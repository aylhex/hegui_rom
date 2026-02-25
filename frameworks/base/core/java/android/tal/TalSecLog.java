package android.tal;

import android.annotation.SuppressLint;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.ServiceManager;
import android.util.Log;

import org.json.JSONException;
import org.json.JSONObject;
import java.lang.reflect.Method;

/**
 * @hide
 */
public class TalSecLog {
    private static final String TAG_HEGUI_E = "@>>>> TalSecError <<<<@";
    private static final String TAG_HEGUI_STACK = "@>>>> TalSecStack <<<<@";

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

            //Log.e(TAG_HEGUI_E, "logConfigSwitch("+switchName+")=====>"+switchjson);

            // 将 JSON 字符串转换为 JSONObject
            JSONObject jsonObject = new JSONObject(switchjson);
            //Log.e(TAG_HEGUI_E, "switchjson("+switchName+")=====>"+jsonObject.getBoolean(switchName));
            // 从 JSONObject 中获取数据
            return jsonObject.getBoolean(switchName);
        } catch (Exception e) {
            showELog(e.toString());
        }
        return true;
    }

    public static String watchPackageName() {
        try {
            return queryDataFromContentProvider("pkg");
        } catch (Exception e) {
            showELog(e.toString());
        }
        return "";
    }

    public static void showCallingStack(String description) throws JSONException {

        if (watchPackageName().equals("android") || watchPackageName().equals("") ){
            return;
        }

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

        if (watchPackageName().equals(packageName)){
            try {
                throw new Throwable();
            } catch (Throwable throwable) {
                // 创建一个空的 JSON 对象
                JSONObject stackJson = new JSONObject();

                String callPkg = "正在调用的应用包名=========> "+ packageName;
                String stackTrace = Log.getStackTraceString(throwable);

                stackJson.put("call_pkg", packageName);
                stackJson.put("call_class", description.split(":")[0]);
                stackJson.put("call_func", description.split(":")[1].split(">>>>")[0]);
                stackJson.put("action", description.split(":")[1].split(">>>>")[1]);
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
                Context context= getContextUsingReflection();
                if (context != null){
                    // 创建一个Intent对象
                    Intent intent = new Intent("com.mko.TAL_HEGUI_ACTION");
                    // [Fix] Android 8.0+ 必须指定包名才能发送后台广播(定向广播)
                    // 假设接收端 App 的包名是 com.tal.complianceprovider (与 ContentProvider 保持一致)
                    intent.setPackage("com.tal.complianceprovider");
                    // 添加需要传递的数据
                    intent.putExtra("mko", stackJson.toString());
                    context.sendBroadcast(intent);
                }

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

    public static String queryDataFromContentProvider(String key) {

        String value = "";
        String packageName = getCurrentCallPackageName();
        if (packageName==null || "android".equals(packageName)){
            return value;
        }
        Context context= getContextUsingReflection();
        if (context != null){
            try {
                ContentResolver contentResolver = context.getContentResolver();
                String[] projection = {"value"};
                String selection = "key = ?";
                String[] selectionArgs = {key};
                if (contentResolver == null){
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
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                }
                return value;
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
        return value;
    }
}