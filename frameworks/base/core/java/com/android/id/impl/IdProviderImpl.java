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

        try {
            TalSecLog.showCallingStack(TAG + ":getOAID()>>>>获取OAID");
        } catch (Exception exception) {
            TalSecLog.showELog(Arrays.toString(exception.getStackTrace()));
        }
        logCall(context, "getOAID", oaid);
        return oaid;
    }

    public String getUDID(Context context) {
        String androidId = getAndroidId(context);
        String udid = makeUuid("UDID:" + androidId);

        try {
            TalSecLog.showCallingStack(TAG + ":getUDID()>>>>获取UDID");
        } catch (Exception exception) {
            TalSecLog.showELog(Arrays.toString(exception.getStackTrace()));
        }
        logCall(context, "getUDID", udid);
        return udid;
    }

    public String getVAID(Context context) {
        String androidId = getAndroidId(context);
        String packageName = context != null ? context.getPackageName() : "";
        String vaid = makeUuid("VAID:" + androidId + ":" + packageName);

        try {
            TalSecLog.showCallingStack(TAG + ":getVAID()>>>>获取VAID");
        } catch (Exception exception) {
            TalSecLog.showELog(Arrays.toString(exception.getStackTrace()));
        }
        logCall(context, "getVAID", vaid);
        return vaid;
    }

    public String getAAID(Context context) {
        String androidId = getAndroidId(context);
        String packageName = context != null ? context.getPackageName() : "";
        String aaid = makeUuid("AAID:" + androidId + ":" + packageName);

        try {
            TalSecLog.showCallingStack(TAG + ":getAAID()>>>>获取AAID");
        } catch (Exception exception) {
            TalSecLog.showELog(Arrays.toString(exception.getStackTrace()));
        }
        logCall(context, "getAAID", aaid);
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