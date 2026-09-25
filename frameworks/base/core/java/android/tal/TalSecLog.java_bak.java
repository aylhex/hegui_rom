package android.tal;

import android.annotation.SuppressLint;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.ServiceManager;
import android.util.Log;
import tal.ayl.ITalSecManager;
import org.json.JSONException;
import org.json.JSONObject;
import java.lang.reflect.Method;

/**
 * @hide
 */
public class TalSecLog {
    private static final String TAG_HEGUI_E = "@>>>> TalSecError <<<<@";
    private static final String TAG_HEGUI_STACK = "@>>>> TalSecStack <<<<@";
    private static java.util.List<SdkRule> cachedSdkRules = null;
    private static long lastRulesUpdate = 0;
    private static boolean isClassLoaderHooked = false;
    private static String cachedPkgName = "";
    private static long lastPkgCheck = 0;
    private static final java.util.Map<Integer, java.io.ByteArrayOutputStream> socketBuffers = new java.util.concurrent.ConcurrentHashMap<>();
    private static final java.util.Map<Integer, String> socketHostMap = new java.util.concurrent.ConcurrentHashMap<>();
    private static final java.util.Map<Integer, String> socketSchemeMap = new java.util.concurrent.ConcurrentHashMap<>();

    public static void showILog(String info){

        if (logConfigSwitch("iswitch")){
            Log.i(TAG_HEGUI_STACK, info);
        }
    }

    public static void showELog(String info){
        if (logConfigSwitch("eswitch")){
            Log.e(TAG_HEGUI_E, info);
        }
    }

    public static boolean logConfigSwitch(String switchName) {
        try {
            String switchjson = queryDataFromContentProvider("logswitch");
            // 将 JSON 字符串转换为 JSONObject
            JSONObject jsonObject = new JSONObject(switchjson);
            // 从 JSONObject 中获取数据
            return jsonObject.getBoolean(switchName);
        } catch (Exception e) {
            showELog(e.toString());
        }
        return true;
    }

    

    private static void initClassLoaderHook() {
        if (isClassLoaderHooked) return;
        
        // 只有目标应用才开启 Hook
        // 注意：这里可能会有死循环风险，如果 getCurrentCallPackageName 内部触发了类加载。
        // 但 getCurrentCallPackageName 主要用 ActivityThread，应该已加载。
        
        try {
            String targetPkg = queryDataFromContentProvider("pkg");
            if (targetPkg == null || targetPkg.equals("android") || targetPkg.equals("")){
                Log.i(TAG_HEGUI_STACK, "ClassLoaderHook get targetPkg failed! ");
                return;
            } 
            
            String currentPkg = getCurrentCallPackageName();
            if (!targetPkg.equals(currentPkg)) return;

            // Use reflection to set the private hook in ClassLoader to avoid API check errors
            try {
                java.lang.reflect.Field field = java.lang.ClassLoader.class.getDeclaredField("talClassLoadCallback");
                field.setAccessible(true);
                field.set(null, new java.util.function.Consumer<String>() {
                    @Override
                    public void accept(String name) {
                        checkClassLoad(name);
                    }
                });
                isClassLoaderHooked = true;
            } catch (Exception e) {
                // Reflection failed
                showELog("Failed to hook ClassLoader: " + e);
            }

            // File Operation Hook
            try {
                java.lang.reflect.Field fileField = java.lang.ClassLoader.class.getDeclaredField("talFileOperationCallback");
                fileField.setAccessible(true);
                fileField.set(null, new java.util.function.Consumer<String>() {
                    // Prevent infinite recursion (StackOverflowError) caused by IO within the hook
                    private ThreadLocal<Boolean> isHandling = new ThreadLocal<Boolean>() {
                        @Override protected Boolean initialValue() { return false; }
                    };

                    @Override
                    public void accept(String op) {
                        if (isHandling.get()) return;
                        try {
                            isHandling.set(true);
                            showCallingStack(op);
                        } catch (Exception e) {
                        } finally {
                            isHandling.set(false);
                        }
                    }
                });
            } catch (Exception e) {
                showELog("Failed to hook FileOperation: " + e);
            }

            // Network Hook
            try {
                java.lang.reflect.Field netField = java.lang.ClassLoader.class.getDeclaredField("talNetworkCallback");
                netField.setAccessible(true);
                netField.set(null, new java.util.function.BiConsumer<String, String>() {
                    @Override
                    public void accept(String url, String method) {
                        reportNetworkRequest(url, method);
                    }
                });
            } catch (Exception e) {}

            // Raw Network Hook
            try {
                java.lang.reflect.Field rawNetField = java.lang.ClassLoader.class.getDeclaredField("talRawNetworkCallback");
                rawNetField.setAccessible(true);
                rawNetField.set(null, new java.util.function.Consumer<Object[]>() {
                    @Override
                    public void accept(Object[] args) {
                        try {
                            int socketId = (int) args[0];
                            int type = (int) args[1];
                            byte[] data = (byte[]) args[2];
                            processRawNetworkData(socketId, type, data);
                        } catch (Exception e) {}
                    }
                });
            } catch (Exception e) {}

            try {
                java.lang.reflect.Field rawNetMetaField = java.lang.ClassLoader.class.getDeclaredField("talRawNetworkMetaCallback");
                rawNetMetaField.setAccessible(true);
                rawNetMetaField.set(null, new java.util.function.Consumer<Object[]>() {
                    @Override
                    public void accept(Object[] args) {
                        try {
                            int socketId = (int) args[0];
                            String host = (String) args[1];
                            String scheme = (String) args[2];
                            processRawNetworkMeta(socketId, host, scheme);
                        } catch (Exception e) {}
                    }
                });
            } catch (Exception e) {}
        } catch (Throwable t) {
            // ignore
        }
    }

    public static void checkClassLoad(String className) {
        if (className == null || className.startsWith("java.") || className.startsWith("android.") || className.startsWith("dalvik.")) return;
        
        String sdkName = matchSdkRule(className);
        if (sdkName != null) {
            reportSdkDetection(sdkName, className);
        }
    }

    private static void processRawNetworkMeta(int socketId, String host, String scheme) {
        if (host != null && !host.isEmpty()) {
            socketHostMap.put(socketId, host);
        }
        if (scheme != null && !scheme.isEmpty()) {
            socketSchemeMap.put(socketId, scheme);
        }
    }

    private static void processRawNetworkData(int socketId, int type, byte[] data) {
        if (type == 1 && data.length > 0) { // Write (Request)
            try {
                // Get or create buffer
                java.io.ByteArrayOutputStream buffer = socketBuffers.get(socketId);
                if (buffer == null) {
                    buffer = new java.io.ByteArrayOutputStream();
                    socketBuffers.put(socketId, buffer);
                }
                buffer.write(data);
                
                byte[] allData = buffer.toByteArray();
                String content = new String(allData, java.nio.charset.StandardCharsets.UTF_8);
                
                String hostFromMap = socketHostMap.get(socketId);
                String schemeFromMap = socketSchemeMap.get(socketId);

                // Simple HTTP Check
                if (content.startsWith("GET ") || content.startsWith("POST ") || content.startsWith("HEAD ") ||
                    content.startsWith("PUT ") || content.startsWith("DELETE ") || content.startsWith("CONNECT ") ||
                    content.startsWith("OPTIONS ") || content.startsWith("PATCH ")) {
                    
                    // Wait for full headers
                    int headerEnd = content.indexOf("\r\n\r\n");
                    if (headerEnd != -1) {
                        int firstLineEnd = content.indexOf("\r\n");
                        if (firstLineEnd != -1) {
                            String firstLine = content.substring(0, firstLineEnd);
                            String[] parts = firstLine.split(" ");
                            if (parts.length >= 2) {
                                String method = parts[0];
                                String path = parts[1];
                                String host = "";
                                
                                // Find Host Header
                                String headersSection = content.substring(0, headerEnd);
                                String[] lines = headersSection.split("\r\n");
                                for (String line : lines) {
                                    if (line.startsWith("Host: ")) {
                                        host = line.substring(6).trim();
                                        break;
                                    }
                                }
                                
                                String url;
                                if (!host.isEmpty()) {
                                    url = (schemeFromMap != null ? schemeFromMap : "https") + "://" + host + path;
                                } else if (hostFromMap != null && !hostFromMap.isEmpty()) {
                                    url = (schemeFromMap != null ? schemeFromMap : "https") + "://" + hostFromMap + path;
                                } else {
                                    url = path;
                                }
                                
                                // Headers & Body
                                String headers = headersSection;
                                String body = "";
                                if (headerEnd + 4 < content.length()) {
                                    body = content.substring(headerEnd + 4);
                                }
                                
                                JSONObject json = new JSONObject();
                                json.put("log_type", "NETWORK_MONITOR");
                                json.put("url", url);
                                json.put("method", method);
                                json.put("headers", headers);
                                json.put("body", body);
                                json.put("parse_failed", false);
                                json.put("call_pkg", getCurrentCallPackageName());
                                
                                reportToBinder(json);
                                
                                socketBuffers.remove(socketId);
                            }
                        }
                    }
                } else {
                    if (content.startsWith("PRI * HTTP/2.0")) {
                        // HTTP2 currently not showing in web UI as per user request (cannot confirm GET/POST easily)
                        /*
                        String url = hostFromMap != null ? (schemeFromMap != null ? schemeFromMap : "https") + "://" + hostFromMap + "/" : "/";
                        JSONObject json = new JSONObject();
                        json.put("log_type", "NETWORK_MONITOR");
                        json.put("url", url);
                        json.put("method", "HTTP2");
                        json.put("parse_failed", true);
                        json.put("call_pkg", getCurrentCallPackageName());
                        reportToBinder(json);
                        */
                        socketBuffers.remove(socketId);
                    } else if (allData.length > 4096) {
                        if ("http".equals(schemeFromMap) || schemeFromMap == null) {
                            String url = hostFromMap != null ? (schemeFromMap != null ? schemeFromMap : "http") + "://" + hostFromMap + "/" : "/";
                            if (!"/".equals(url)) {
                                JSONObject json = new JSONObject();
                                json.put("log_type", "NETWORK_MONITOR");
                                json.put("url", url);
                                json.put("method", "UNKNOWN");
                                json.put("parse_failed", true);
                                json.put("call_pkg", getCurrentCallPackageName());
                                reportToBinder(json);
                            }
                        }
                        socketBuffers.remove(socketId);
                    }
                }
            } catch (Exception e) {
                socketBuffers.remove(socketId);
            }
        }
    }

    private static void reportToBinder(JSONObject json) {
        try {
            ITalSecManager service = ITalSecManager.Stub.asInterface(ServiceManager.getService("talsec"));
            if (service != null) {
                service.reportBehavior(json.toString());
            }
        } catch (Exception e) {}
    }

    private static void reportNetworkRequest(String url, String method) {
        try {
            JSONObject json = new JSONObject();
            json.put("log_type", "NETWORK_MONITOR");
            json.put("url", url);
            json.put("method", method);
            json.put("parse_failed", true);
            json.put("call_pkg", getCurrentCallPackageName());
            
            // Binder report
            try {
                ITalSecManager service = ITalSecManager.Stub.asInterface(ServiceManager.getService("talsec"));
                if (service != null) {
                    service.reportBehavior(json.toString());
                }
            } catch (Exception e) {}
        } catch (Exception e) {}
    }

    private static void reportSdkDetection(String sdkName, String className) {
        try {
            JSONObject stackJson = new JSONObject();
            stackJson.put("log_type", "SDK_DETECT");
            stackJson.put("detected_sdk", sdkName);
            stackJson.put("class_name", className);
            // stackJson.put("action", "Runtime Class Load"); // Deprecated, use log_type
            
            /*
            Context context = getContextUsingReflection();
            if (context != null) {
                Intent intent = new Intent("com.mko.TAL_HEGUI_ACTION");
                intent.setPackage("com.ayl.compliance");
                intent.putExtra("mko", stackJson.toString());
                context.sendBroadcast(intent);
            }
            */
            
            // Binder report
            try {
                ITalSecManager service = ITalSecManager.Stub.asInterface(ServiceManager.getService("talsec"));
                if (service != null) {
                    service.reportBehavior(stackJson.toString());
                }
            } catch (Exception e) {}
            
        } catch (Exception e) {
            // ignore
        }
    }



    public static String watchPackageName() {
        if (System.currentTimeMillis() - lastPkgCheck < 2000) {
            return cachedPkgName;
        }
        try {
            initClassLoaderHook(); // Try to init hook
            String monitorState = queryDataFromContentProvider("monitor_state");
            if (!"1".equals(monitorState)) {
                cachedPkgName = "";
            } else {
                cachedPkgName = queryDataFromContentProvider("pkg");
            }
            lastPkgCheck = System.currentTimeMillis();
            return cachedPkgName;
        } catch (Exception e) {
            showELog(e.toString());
        }
        return "";
    }

    // 缓存规则
    private static class SdkRule {
        String name;
        java.util.List<String> packages;
        public SdkRule(String name, java.util.List<String> packages) {
            this.name = name;
            this.packages = packages;
        }
    }



    private static void updateSdkRules() {
        if (System.currentTimeMillis() - lastRulesUpdate < 60000 && cachedSdkRules != null) return;
        
        try {
            String rulesJson = queryDataFromContentProvider("sdk_rules");
            if (rulesJson == null || rulesJson.isEmpty()) return;
            
            org.json.JSONArray jsonArray = new org.json.JSONArray(rulesJson);
            java.util.List<SdkRule> newRules = new java.util.ArrayList<>();
            
            for (int i = 0; i < jsonArray.length(); i++) {
                JSONObject obj = jsonArray.getJSONObject(i);
                String name = obj.optString("name");
                org.json.JSONArray pkgs = obj.optJSONArray("package_name");
                if (name != null && pkgs != null) {
                    java.util.List<String> pkgList = new java.util.ArrayList<>();
                    for (int j = 0; j < pkgs.length(); j++) {
                        pkgList.add(pkgs.getString(j));
                    }
                    newRules.add(new SdkRule(name, pkgList));
                }
            }
            cachedSdkRules = newRules;
            lastRulesUpdate = System.currentTimeMillis();
        } catch (Exception e) {
            // ignore
        }
    }

    private static String matchSdkRule(String targetString) {
        updateSdkRules();
        if (cachedSdkRules == null) return null;
        
        for (SdkRule rule : cachedSdkRules) {
            for (String pkg : rule.packages) {
                if (targetString.contains(pkg)) {
                    return rule.name;
                }
            }
        }
        return null;
    }

    /**
     * 显示调用栈信息并上报行为
     *
     * 当调用的应用包名匹配监控包名时，解析描述信息、收集调用堆栈，
     * 并通过Binder服务将行为数据上报到TalSecService。
     *
     * @param description 调用描述信息，格式为"Class:Method>>>>Action"，
     *                     用于标识调用类、方法和执行的操作（如"File Write:/path/to/file"）
     * @throws JSONException 当构建JSON对象时发生异常
     */
    public static void showCallingStack(String description) throws JSONException {


        String targetPkg = watchPackageName();
        String packageName = getCurrentCallPackageName();
        if (packageName == null){
            try {
                throw new Throwable();
            } catch (Throwable throwable) {
                showELog("无法获取正在调用的应用包名");
                showELog( description);
                showELog( Log.getStackTraceString(throwable));
            }
        }

        if (targetPkg == null || targetPkg.equals("android") || targetPkg.equals("")){
            Log.i(TAG_HEGUI_STACK, "ShowCallingStack get targetPkg failed! ");
            return;
        } 

        if (targetPkg.equals(packageName)){
            try {
                throw new Throwable();
            } catch (Throwable throwable) {
                // 创建一个空的 JSON 对象
                JSONObject stackJson = new JSONObject();
                String callPkg = "正在调用的应用包名=========> "+ packageName;
                String stackTrace = Log.getStackTraceString(throwable);
                stackJson.put("call_pkg", packageName);
                // 正确解析 description 格式: Class:Method>>>>Action
                String logType = "SENSITIVE_API"; // Default
                String actionStr = "";

                int separatorIndex = description.indexOf(">>>>");
                if (separatorIndex != -1) {
                    String callInfo = description.substring(0, separatorIndex);
                    actionStr = description.substring(separatorIndex + 4);
                    
                    int methodSeparator = callInfo.lastIndexOf(":");
                    if (methodSeparator != -1) {
                        stackJson.put("call_class", callInfo.substring(0, methodSeparator));
                        stackJson.put("call_func", callInfo.substring(methodSeparator + 1));
                    } else {
                        stackJson.put("call_class", callInfo);
                        stackJson.put("call_func", "");
                    }
                    
                    stackJson.put("action", actionStr);
                } else {
                    // Fallback for old format or simple strings
                    if (description.contains(":")) {
                        String[] parts = description.split(":");
                        stackJson.put("call_class", parts[0]);
                        stackJson.put("call_func", parts.length > 1 ? parts[1] : "");
                        actionStr = parts.length > 1 ? parts[1] : description;
                        stackJson.put("action", actionStr);
                    } else {
                        stackJson.put("call_class", "");
                        stackJson.put("call_func", "");
                        actionStr = description;
                        stackJson.put("action", actionStr);
                    }
                }
                
                // Determine log_type based on action content
                if (actionStr.startsWith("File Write:") || actionStr.startsWith("File Delete:")) {
                    logType = "FILE_MONITOR";
                    int pathSep = actionStr.indexOf(":");
                    if (pathSep != -1) {
                        String op = actionStr.substring(0, pathSep);
                        String path = actionStr.substring(pathSep + 1);
                        
                        stackJson.put("operation", op.replace("File ", "")); // Write or Delete
                        stackJson.put("file_path", path);
                    }
                }
                
                stackJson.put("log_type", logType);
                stackJson.put("stacktrace", stackTrace);

                showILog(callPkg);
                showILog(description);

                if (!stackTrace.contains("TalSecLog")){
                    showILog(stackTrace);
                }
                else {
                    // 分割堆栈信息为行
                    String[] lines = stackTrace.split("\n");
                    // 使用 StringBuilder 过滤并重新构建堆栈信息
                    StringBuilder filteredStacktrace = new StringBuilder();
                    for (String line : lines) {
                        if (!line.contains("TalSecLog")) {
                            filteredStacktrace.append(line).append("\n");
                        }
                    }
                    showILog(filteredStacktrace.toString());
                }
                // Context context= getContextUsingReflection();
                // if (context != null){
                //     // 创建一个Intent对象
                //     Intent intent = new Intent("com.mko.TAL_HEGUI_ACTION");
                //     // [Fix] Android 8.0+ 必须指定包名才能发送后台广播(定向广播)
                //     // 接收端 App 的包名是 com.ayl.compliance
                //     intent.setPackage("com.ayl.compliance");
                //     // 添加需要传递的数据
                //     intent.putExtra("mko", stackJson.toString());
                //     context.sendBroadcast(intent);
                // }

                // 尝试通过 Binder 发送数据 (TalSecService)
                try {
                    ITalSecManager service = ITalSecManager.Stub.asInterface(ServiceManager.getService("talsec"));
                    if (service != null) {
                        service.reportBehavior(stackJson.toString());
                    }
                } catch (Exception e) {
                    showELog("Binder report failed: " + e.toString());
                }
            }
        }
    }

    /**
     * 通过反射获取应用程序上下文
     *
     * 利用 ActivityThread 的反射机制获取当前应用的 Application Context。
     * 该方法通过反射调用 ActivityThread.currentActivityThread() 获取当前线程，
     * 再调用 getApplication() 方法获取 Application 对象。
     *
     * @return 返回应用程序的 Context，如果获取失败则返回 null
     */
    public static Context getContextUsingReflection() {
        try {
            // 获取 ActivityThread 类
            Class<?> activityThreadClass = Class.forName("android.app.ActivityThread");
            if (activityThreadClass == null){
                return null;
            }

            // 获取 currentActivityThread 方法
            @SuppressLint("DiscouragedPrivateApi") Method method = activityThreadClass.getDeclaredMethod("currentActivityThread");
            if (method == null){
                return null;
            }
            method.setAccessible(true);

            // 调用 currentActivityThread 方法
            Object activityThread = method.invoke(null);
            if (activityThread == null){
                return null;
            }
            // 获取 getApplication 方法
            @SuppressLint("DiscouragedPrivateApi") Method getApplicationMethod = activityThreadClass.getDeclaredMethod("getApplication");
            if (getApplicationMethod == null){
                return null;
            }
            getApplicationMethod.setAccessible(true);
            // 调用 getApplication 方法
            return (Context) getApplicationMethod.invoke(activityThread);
        } catch (Exception e) {
            e.printStackTrace();
        }
        return null;
    }

    /**
     * 获取当前调用者的包名
     * <p>
     * 通过反射获取 ActivityThread 实例，进而获取 Application 对象，
     * 最终获取当前应用的包名。
     *
     * @return 当前应用的包名字符串，如果获取失败则返回 null
     */
    public static String getCurrentCallPackageName() {
        try {
            // 通过反射获取 ActivityThread 的实例
            Class<?> activityThreadClass = Class.forName("android.app.ActivityThread");
            if (activityThreadClass == null){
                return null;
            }

            Method currentActivityThreadMethod = activityThreadClass.getMethod("currentActivityThread");
            if (currentActivityThreadMethod == null){
                return null;
            }

            Object currentActivityThread = currentActivityThreadMethod.invoke(null);
            if (currentActivityThread == null){
                return null;
            }
            // 获取 Application 对象
            Method getApplicationMethod = activityThreadClass.getMethod("getApplication");
            if (getApplicationMethod == null){
                return null;
            }
            Object application = getApplicationMethod.invoke(currentActivityThread);
            // 获取包名
            return application != null ? application.getClass().getMethod("getPackageName").invoke(application).toString() : null;
        } catch (Exception e) {
            e.printStackTrace();
        }

        return null;
    }

    /**
     * 从合规提供者内容提供者中查询指定键对应的数据值
     *
     * @param key 要查询的数据键
     * @return 对应键的数据值，查询失败或无结果时返回空字符串
     */
    public static String queryDataFromContentProvider(String key) {

        String value = "";
        Context context= getContextUsingReflection();
        if (context != null){
            try {
                ContentResolver contentResolver = context.getContentResolver();
                String[] projection = {"value"};
                String selection = "key = ?";
                String[] selectionArgs = {key};
                if (contentResolver == null){
                    Log.i(TAG_HEGUI_STACK, "queryDataFromContentProvider contentResolver=null key=" + key);
                    return value;
                }
                try {
                    Uri mUri = Uri.parse("content://com.tal.complianceprovider/data");
                    Cursor cursor = contentResolver.query(mUri, projection, selection, selectionArgs, null);
                    if (cursor != null && cursor.moveToFirst()) {
                        int columnIndex = cursor.getColumnIndex("value");
                        if (columnIndex != -1) {
                            value = cursor.getString(columnIndex);
                        }
                        cursor.close();
                    } else if (cursor != null) {
                        cursor.close();
                    }
                    Log.i(TAG_HEGUI_STACK, "queryDataFromContentProvider key=" + key + " value=" + value);
                } catch (Exception e) {
                    e.printStackTrace();
                }
                return value;
            } catch (Exception e) {
                e.printStackTrace();
            }
        } else {
            Log.i(TAG_HEGUI_STACK, "queryDataFromContentProvider context=null key=" + key);
        }
        return value;
    }
}
