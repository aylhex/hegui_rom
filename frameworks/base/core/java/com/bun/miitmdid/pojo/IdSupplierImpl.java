package com.bun.miitmdid.pojo;

import com.bun.miitmdid.interfaces.IdSupplier;

public class IdSupplierImpl implements IdSupplier {
    private final String oaid;
    private final String vaid;
    private final String aaid;
    private final boolean supported;
    private final boolean limited;
    private final boolean supportRequestOaidPermission;

    public IdSupplierImpl(String oaid, String vaid, String aaid, boolean supported, boolean limited, boolean supportRequestOaidPermission) {
        this.oaid = oaid;
        this.vaid = vaid;
        this.aaid = aaid;
        this.supported = supported;
        this.limited = limited;
        this.supportRequestOaidPermission = supportRequestOaidPermission;
    }

    @Override
    public boolean isSupported() {
        return supported;
    }

    @Override
    public boolean isLimited() {
        return limited;
    }

    @Override
    public boolean isSupportRequestOAIDPermission() {
        return supportRequestOaidPermission;
    }

    @Override
    public String getOAID() {
        return oaid;
    }

    @Override
    public String getVAID() {
        return vaid;
    }

    @Override
    public String getAAID() {
        return aaid;
    }
}
