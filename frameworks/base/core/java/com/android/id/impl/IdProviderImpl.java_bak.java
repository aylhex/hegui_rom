package com.android.id.impl;

import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Binder;
import android.provider.Settings;
import android.text.TextUtils;
import android.tal.TalSecLog;
import android.util.Log;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.UUID;

public class IdProviderImpl {
    private static final String TAG = "IdProviderImpl";

    public String getOAID(Context context) {
        String androidId = getAndroidId(context);
        String oaid = makeUuid("OAID:" + androidId);
        logCallingStack(TAG + ":getOAID()>>>>获取ODIA", context, "getOAID", oaid);
        return oaid;
    }

    public String getUDID(Context context) {
        String androidId = getAndroidId(context);
        String udid = makeUuid("UDID:" + androidId);
        logCallingStack(TAG + ":getUDID()>>>>获取UDID", context, "getUDID", udid);
        return udid;
    }

    public String getVAID(Context context) {
        String androidId = getAndroidId(context);
        String packageName = context != null ? context.getPackageName() : "";
        String vaid = makeUuid("VAID:" + androidId + ":" + packageName);
        logCallingStack(TAG + ":getVAID()>>>>获取VAID", context, "getVAID", vaid);
        return vaid;
    }

    public String getAAID(Context context) {
        String androidId = getAndroidId(context);
        String packageName = context != null ? context.getPackageName() : "";
        String aaid = makeUuid("AAID:" + androidId + ":" + packageName);
        logCallingStack(TAG + ":getAAID()>>>>获取AAID", context, "getAAID", aaid);
        return aaid;
    }

    private static String getAndroidId(Context context) {
        if (context == null) {
            return "unknown";
        }
        String androidId = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID);
        if (TextUtils.isEmpty(androidId)) {
            return "unknown";
        }
        return androidId;
    }

    private static String makeUuid(String seed) {
        return UUID.nameUUIDFromBytes(seed.getBytes(StandardCharsets.UTF_8)).toString();
    }

    private static void logCallingStack(String description, Context context, String method, String value) {
        try {
            TalSecLog.showCallingStack(description);
        } catch (Exception exception) {
            logCall(context, method + " error ", Arrays.toString(exception.getStackTrace()));
        }
        // String watchPkg = TalSecLog.watchPackageName();
        // String callPkg = TalSecLog.getCurrentCallPackageName();
        // if (watchPkg == null || watchPkg.isEmpty() || callPkg == null || !watchPkg.equals(callPkg)) {
        //     TalSecLog.showILog(description);
        //     TalSecLog.showILog("call_pkg=" + (callPkg == null ? "" : callPkg) + " watch_pkg=" + (watchPkg == null ? "" : watchPkg));
        //     TalSecLog.showILog(Log.getStackTraceString(new Throwable()));
        // }
        logCall(context, method, value);
    }

    private static void logCall(Context context, String method, String value) {
        
        String callerPkg = getCallerPackage(context);
        Log.i(TAG, "OAID_CALL method=" + method + " call_pkg=" + callerPkg + " value=" + value);
    }

    private static String getCallerPackage(Context context) {
        int uid = Binder.getCallingUid();
        if (context == null) {
            return "";
        }
        PackageManager pm = context.getPackageManager();
        String[] pkgs = pm.getPackagesForUid(uid);
        if (pkgs != null && pkgs.length > 0) {
            return pkgs[0];
        }
        return context.getPackageName();
    }
}
