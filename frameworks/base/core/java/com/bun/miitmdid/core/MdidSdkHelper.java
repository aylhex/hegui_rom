package com.bun.miitmdid.core;

import android.content.Context;
import com.android.id.impl.IdProviderImpl;
import com.bun.miitmdid.interfaces.IIdentifierListener;
import com.bun.miitmdid.interfaces.IdSupplier;
import com.bun.miitmdid.pojo.IdSupplierImpl;

public class MdidSdkHelper {
    public static final int SDK_VERSION_CODE = 202203;
    private static final int INIT_INFO_RESULT_OK = 1008610;
    private static long globalTimeout = 5000;

    public static boolean setGlobalTimeout(long timeout) {
        if (timeout <= 0) {
            return false;
        }
        globalTimeout = timeout;
        return true;
    }

    public static boolean InitCert(Context context, String str) {
        return true;
    }

    public static int InitSdk(Context context, boolean z, IIdentifierListener listener) {
        return init(context, listener);
    }

    public static int InitSdk(Context context, boolean z, boolean z2, boolean z3, boolean z4, IIdentifierListener listener) {
        return init(context, listener);
    }

    public static void requestOAIDPermission(Context context, com.bun.miitmdid.interfaces.IPermissionCallbackListener listener) {
        if (listener == null) {
            return;
        }
        int pid = android.os.Process.myPid();
        String pkg = context != null ? context.getPackageName() : "";
        listener.onAllowed(pkg, pid);
        listener.onGranted(pkg, pid);
    }

    private static int init(Context context, IIdentifierListener listener) {
        if (listener == null) {
            return 1008615;
        }
        IdProviderImpl provider = new IdProviderImpl();
        String oaid = provider.getOAID(context);
        String vaid = provider.getVAID(context);
        String aaid = provider.getAAID(context);
        IdSupplier supplier = new IdSupplierImpl(oaid, vaid, aaid, true, true, true);
        notifySupport(listener, supplier);
        return INIT_INFO_RESULT_OK;
    }

    private static void notifySupport(Object listener, IdSupplier supplier) {
        if (listener == null) {
            return;
        }
        try {
            java.lang.reflect.Method method = listener.getClass().getMethod("onSupport", IdSupplier.class);
            method.invoke(listener, supplier);
            return;
        } catch (Throwable ignored) {
        }
        try {
            java.lang.reflect.Method method = listener.getClass().getMethod("OnSupport", IdSupplier.class);
            method.invoke(listener, supplier);
            return;
        } catch (Throwable ignored) {
        }
        try {
            java.lang.reflect.Method method = listener.getClass().getMethod("onSupport", boolean.class, IdSupplier.class);
            method.invoke(listener, true, supplier);
            return;
        } catch (Throwable ignored) {
        }
        try {
            java.lang.reflect.Method method = listener.getClass().getMethod("OnSupport", boolean.class, IdSupplier.class);
            method.invoke(listener, true, supplier);
        } catch (Throwable ignored) {
        }
    }
}
