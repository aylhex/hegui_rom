package frameworks.base.core.java.tal.ayl;

import android.content.Context;
import android.os.RemoteException;
import tal.ayl.IMKOService;

public class MKOServiceManger {

    private final Context mContext;
    private final IMKOService mService;

    public MKOServiceManger(Context mContext, IMKOService imkoService) {
        this.mContext = mContext;
        this.mService = imkoService;
    }

    public String queryWatchPackage(String key){
        try {
            return mService.queryWatchPackage(key);
        } catch (RemoteException e) {
            e.printStackTrace();
        }
		return "Error";
    }

    public String setWatchPackage(String packageName){
        try {
            return mService.setWatchPackage(packageName);
        } catch (RemoteException e) {
            e.printStackTrace();
        }
		return "Error";
    }
}
