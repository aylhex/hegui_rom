package android.tal;

import android.content.Context;
import android.os.Binder;
import android.os.IBinder;
import android.os.RemoteCallbackList;
import android.os.RemoteException;
import android.util.Log;
import tal.ayl.ITalSecManager;
import tal.ayl.ITalSecListener;

/**
 * System service for TalSec security logging.
 * @hide
 */
public class TalSecService extends ITalSecManager.Stub {
    private static final String TAG = "TalSecService";
    private final Context mContext;
    // Thread-safe callback list for managing listeners across processes
    private final RemoteCallbackList<ITalSecListener> mListeners = new RemoteCallbackList<>();

    public TalSecService(Context context) {
        mContext = context;
    }

    @Override
    public void reportBehavior(String json) {
        // Broadcast the reported behavior to all registered listeners
        // This is safe to call from any thread
        final int n = mListeners.beginBroadcast();
        try {
            for (int i = 0; i < n; i++) {
                try {
                    mListeners.getBroadcastItem(i).onBehavior(json);
                } catch (RemoteException e) {
                    // The RemoteCallbackList will handle dead objects automatically
                    Log.e(TAG, "Error notifying listener", e);
                }
            }
        } finally {
            mListeners.finishBroadcast();
        }
    }

    @Override
    public void registerListener(ITalSecListener listener) {
        // Ideally, we should check for a specific permission here
        // mContext.enforceCallingOrSelfPermission("android.permission.READ_LOGS", "Need permission to listen to TalSec logs");
        
        if (listener != null) {
            mListeners.register(listener);
            Log.i(TAG, "Listener registered: " + Binder.getCallingPid());
        }
    }

    @Override
    public void unregisterListener(ITalSecListener listener) {
        if (listener != null) {
            mListeners.unregister(listener);
            Log.i(TAG, "Listener unregistered: " + Binder.getCallingPid());
        }
    }
}
