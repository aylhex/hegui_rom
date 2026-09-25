package android.tal;

import android.annotation.SuppressLint;
import android.content.ContentResolver;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.util.Log;
import org.json.JSONException;
import org.json.JSONObject;
import java.lang.reflect.Method;

/**
 * @hide
 */
public class TalSecLog {
    private static final String TAG_HEGUI_E = "@>>>> AylSecError <<<<@";
    private static final String TAG_HEGUI_STACK = "@>>>> AylSecStack <<<<@";
    private static java.util.List<SdkRule> cachedSdkRules = null;
    private static long lastRulesUpdate = 0;
    private static boolean isClassLoaderHooked = false;
    private static String cachedPkgName = "";
    private static long lastPkgCheck = 0;
    private static final java.util.Map<Integer, java.io.ByteArrayOutputStream> socketBuffers = new java.util.concurrent.ConcurrentHashMap<>();
    private static final java.util.Map<Integer, String> socketHostMap = new java.util.concurrent.ConcurrentHashMap<>();
    private static final java.util.Map<Integer, String> socketSchemeMap = new java.util.concurrent.ConcurrentHashMap<>();
    private static final ThreadLocal<Boolean> LOG_SWITCH_CHECKING = new ThreadLocal<Boolean>() {
        @Override
        protected Boolean initialValue() {
            return false;
        }
    };

    public static void showILog(String info){
        if (LOG_SWITCH_CHECKING.get()) {
            Log.i(TAG_HEGUI_STACK, info);
            return;
        }
        if (logConfigSwitch()){
            Log.i(TAG_HEGUI_STACK, info);
        }
    }

    public static void showELog(String info){
        if (LOG_SWITCH_CHECKING.get()) {
            Log.e(TAG_HEGUI_E, info);
            return;
        }
        if (logConfigSwitch()){
            Log.e(TAG_HEGUI_E, info);
        }
    }

    public static boolean logConfigSwitch() {
        if (LOG_SWITCH_CHECKING.get()) {
            return true;
        }
        LOG_SWITCH_CHECKING.set(true);
        try {
            String logswitch = queryDataFromContentProvider("logswitch");
            // 获取的值不为1，均认为开关为关
            if ("1".equals(logswitch)){
                return true;
            }
            return false;
        } catch (Exception e) {
            Log.e(TAG_HEGUI_E, "logConfigSwitch failed: " + e.toString());
            // 用于在异常情况，可以临时输出错误日志
            return true;
        } finally {
            LOG_SWITCH_CHECKING.set(false);
        }
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
                            TalSecService.reportNetworkRequest(url, method, getCurrentCallPackageName());
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
            TalSecService.reportSdkDetection(sdkName, className);
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
                if (isHttpMethod(content)) {
                    JSONObject json = buildNetworkJson(content, hostFromMap, schemeFromMap, getCurrentCallPackageName());
                    if (json != null) {
                        TalSecService.reportBehaviorJson(json);
                        socketBuffers.remove(socketId);
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
                                TalSecService.reportBehaviorJson(json);
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

    private static boolean isHttpMethod(String content) {
        return content.startsWith("GET ") || content.startsWith("POST ") || content.startsWith("HEAD ") ||
            content.startsWith("PUT ") || content.startsWith("DELETE ") || content.startsWith("CONNECT ") ||
            content.startsWith("OPTIONS ") || content.startsWith("PATCH ");
    }

    private static JSONObject buildNetworkJson(String content, String hostFromMap, String schemeFromMap, String callPkg) throws JSONException {
        ParsedHttpRequest parsed = parseHttpRequest(content, hostFromMap, schemeFromMap);
        if (parsed == null) {
            return null;
        }
        JSONObject json = new JSONObject();
        json.put("log_type", "NETWORK_MONITOR");
        json.put("url", parsed.url);
        json.put("method", parsed.method);
        json.put("headers", parsed.headers);
        json.put("body", parsed.body);
        json.put("parse_failed", false);
        json.put("call_pkg", callPkg);
        return json;
    }

    private static ParsedHttpRequest parseHttpRequest(String content, String hostFromMap, String schemeFromMap) {
        int headerEnd = content.indexOf("\r\n\r\n");
        if (headerEnd == -1) {
            return null;
        }
        int firstLineEnd = content.indexOf("\r\n");
        if (firstLineEnd == -1) {
            return null;
        }
        String firstLine = content.substring(0, firstLineEnd);
        String[] parts = firstLine.split(" ");
        if (parts.length < 2) {
            return null;
        }
        String method = parts[0];
        String path = parts[1];

        String headersSection = content.substring(0, headerEnd);
        String host = "";
        String[] lines = headersSection.split("\r\n");
        for (String line : lines) {
            if (line.startsWith("Host: ")) {
                host = line.substring(6).trim();
                break;
            }
        }

        String scheme = schemeFromMap != null ? schemeFromMap : "https";
        String url;
        if (!host.isEmpty()) {
            url = scheme + "://" + host + path;
        } else if (hostFromMap != null && !hostFromMap.isEmpty()) {
            url = scheme + "://" + hostFromMap + path;
        } else {
            url = path;
        }

        String body = "";
        if (headerEnd + 4 < content.length()) {
            body = content.substring(headerEnd + 4);
        }
        return new ParsedHttpRequest(method, url, headersSection, body);
    }

    private static final class ParsedHttpRequest {
        final String method;
        final String url;
        final String headers;
        final String body;

        ParsedHttpRequest(String method, String url, String headers, String body) {
            this.method = method;
            this.url = url;
            this.headers = headers;
            this.body = body;
        }
    }

    public static String watchPackageName() {
        if (System.currentTimeMillis() - lastPkgCheck < 2000) {
            return cachedPkgName;
        }
        try {
            initClassLoaderHook(); // Try to init hook
            // [AylSec] Changed to read from SystemProperties for extreme speed and safety
            String monitorState = android.os.SystemProperties.get("persist.sys.aylsec.monitor", "0");
            if (!"1".equals(monitorState)) {
                cachedPkgName = "";
            } else {
                cachedPkgName = android.os.SystemProperties.get("persist.sys.aylsec.target", "");
            }
            lastPkgCheck = System.currentTimeMillis();
            return cachedPkgName;
        } catch (Exception e) {
            Log.i(TAG_HEGUI_STACK, "watchPackageName failed: " + e.toString());
        }
        return cachedPkgName;
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
        // System booting protection: avoid doing heavy reflection and logging in early boot
        if (LOG_SWITCH_CHECKING.get()) {
            return;
        }
        
        String targetPkg = watchPackageName();
        String packageName = getCurrentCallPackageName();
        if (packageName == null || targetPkg.isEmpty() || targetPkg.equals("android")) {
            return;
        }
        
        if (targetPkg.equals(packageName)){
            Throwable throwable = new Throwable();
            String stackTrace = Log.getStackTraceString(throwable);
            
            // [AylSec] Check if the stack trace is suspiciously short (possibly truncated by reflection or async thread)
            // A normal app call stack is usually much deeper than 5 frames.
            if (throwable.getStackTrace().length < 5) {
                StringBuilder extendedStack = new StringBuilder();
                try {
                    // 1. Call the native physical stack trace to bypass reflection filters
                    String nativeStack = dalvik.system.VMStack.getNativePhysicalStackTrace();
                    if (nativeStack != null && !nativeStack.isEmpty()) {
                        extendedStack.append("=== Native 层调用堆栈信息===\n")
                                     .append(nativeStack).append("\n");
                    }
                    
                    // 2. [AylSec Strategy A] Dump all threads to catch async dispatchers
                    extendedStack.append("=== 当前目标应用活跃线程的堆栈信息(疑似调用相关) ===\n");
                    java.util.Map<Thread, StackTraceElement[]> allThreads = Thread.getAllStackTraces();
                    Thread currentThread = Thread.currentThread();
                    
                    for (java.util.Map.Entry<Thread, StackTraceElement[]> entry : allThreads.entrySet()) {
                        Thread t = entry.getKey();
                        // Skip system/daemon threads that are irrelevant
                        if (t.isDaemon() || t == currentThread || t.getName().startsWith("Binder") 
                            || t.getName().startsWith("Jit thread") || t.getName().startsWith("Signal Catcher")
                            || t.getName().startsWith("HeapTask")) {
                            continue;
                        }
                        
                        StackTraceElement[] elems = entry.getValue();
                        // Only dump threads that are actively doing something (not just parking/waiting)
                        if (elems != null && elems.length > 0) {
                            // Filter out threads that are purely in native epoll/wait (idle threads)
                            if (elems[0].getClassName().contains("MessageQueue") && elems[0].getMethodName().equals("nativePollOnce")) {
                                continue;
                            }
                            if (elems[0].getClassName().contains("Unsafe") && elems[0].getMethodName().equals("park")) {
                                continue;
                            }
                            if (elems[0].getClassName().contains("Object") && elems[0].getMethodName().equals("wait")) {
                                continue;
                            }
                            
                            extendedStack.append("\n--- Thread: [").append(t.getName()).append("] (State: ").append(t.getState()).append(") ---\n");
                            for (StackTraceElement elem : elems) {
                                extendedStack.append("  at ").append(elem.toString()).append("\n");
                            }
                        }
                    }
                    
                    stackTrace = extendedStack.toString() + "\n=== 原始Java层调用堆栈信息 ===\n" + stackTrace;
                } catch (Throwable t) {
                    // Ignore, fallback to original stackTrace
                }
            }

            JSONObject stackJson = buildStackJson(description, packageName, stackTrace);
            printStackLog(packageName, description, stackTrace);
            try {
                TalSecService.reportBehaviorJson(stackJson);
            } catch (Exception e) {
                Log.i(TAG_HEGUI_STACK, "Binder report failed: " + e.toString());
            }
        }
    }

    private static JSONObject buildStackJson(String description, String packageName, String stackTrace) throws JSONException {
        JSONObject stackJson = new JSONObject();
        stackJson.put("call_pkg", packageName);
        String actionStr = fillCallInfo(stackJson, description);
        fillLogType(stackJson, actionStr);
        stackJson.put("stacktrace", stackTrace);
        return stackJson;
    }

    private static String fillCallInfo(JSONObject stackJson, String description) throws JSONException {
        int separatorIndex = description.indexOf(">>>>");
        if (separatorIndex != -1) {
            String callInfo = description.substring(0, separatorIndex);
            String actionStr = description.substring(separatorIndex + 4);
            int methodSeparator = callInfo.lastIndexOf(":");
            if (methodSeparator != -1) {
                stackJson.put("call_class", callInfo.substring(0, methodSeparator));
                stackJson.put("call_func", callInfo.substring(methodSeparator + 1));
            } else {
                stackJson.put("call_class", callInfo);
                stackJson.put("call_func", "");
            }
            stackJson.put("action", actionStr);
            return actionStr;
        }

        if (description.contains(":")) {
            String[] parts = description.split(":");
            String actionStr = parts.length > 1 ? parts[1] : description;
            stackJson.put("call_class", parts[0]);
            stackJson.put("call_func", parts.length > 1 ? parts[1] : "");
            stackJson.put("action", actionStr);
            return actionStr;
        }

        stackJson.put("call_class", "");
        stackJson.put("call_func", "");
        stackJson.put("action", description);
        return description;
    }

    private static void fillLogType(JSONObject stackJson, String actionStr) throws JSONException {
        String logType = "SENSITIVE_API";
        if (actionStr.startsWith("File Write:") || actionStr.startsWith("File Delete:")) {
            logType = "FILE_MONITOR";
            int pathSep = actionStr.indexOf(":");
            if (pathSep != -1) {
                String op = actionStr.substring(0, pathSep);
                String path = actionStr.substring(pathSep + 1);
                stackJson.put("operation", op.replace("File ", ""));
                stackJson.put("file_path", path);
            }
        }
        stackJson.put("log_type", logType);
    }

    private static void printStackLog(String packageName, String description, String stackTrace) {
        showILog("正在调用的应用包名=========> " + packageName);
        showILog(description);
        if (!stackTrace.contains("TalSecLog")) {
            showILog(stackTrace);
            return;
        }
        String[] lines = stackTrace.split("\n");
        StringBuilder filteredStacktrace = new StringBuilder();
        for (String line : lines) {
            if (!line.contains("TalSecLog")) {
                filteredStacktrace.append(line).append("\n");
            }
        }
        showILog(filteredStacktrace.toString());
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
        // [AylSec] Replace slow ContentProvider query with fast SystemProperties read
        if ("logswitch".equals(key)) {
            return android.os.SystemProperties.get("persist.sys.aylsec.logswitch", "0");
        } else if ("pkg".equals(key)) {
            return android.os.SystemProperties.get("persist.sys.aylsec.target", "");
        } else if ("monitor_state".equals(key)) {
            return android.os.SystemProperties.get("persist.sys.aylsec.monitor", "0");
        }
        
        // For other keys (like sdk_rules), fallback to Provider if needed
        String value = "";
        Context context= getContextUsingReflection();
        if (context != null){
            try {
                ContentResolver contentResolver = context.getContentResolver();
                if (contentResolver == null){
                    return value;
                }
                String[] projection = {"value"};
                String selection = "key = ?";
                String[] selectionArgs = {key};
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
                } catch (Exception e) {
                    // e.printStackTrace();
                }
                return value;
            } catch (Exception e) {
                // e.printStackTrace();
            }
        }

        return value;
    }
}