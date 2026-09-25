package com.bun.miitmdid.interfaces;

public interface IdSupplier {
    boolean isSupported();
    boolean isLimited();
    boolean isSupportRequestOAIDPermission();
    String getOAID();
    String getVAID();
    String getAAID();
}
