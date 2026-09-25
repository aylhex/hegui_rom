package com.bun.miitmdid.interfaces;

public interface IPermissionCallbackListener {
    default void onAllowed(String pkgName, int pid) {
    }

    default void onDenied(String pkgName, int pid) {
    }

    default void onGranted(String pkgName, int pid) {
    }

    default void onAskAgain(String pkgName, int pid) {
    }
}
