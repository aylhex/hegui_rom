package tal.ayl;

import tal.ayl.ITalSecListener;

/** @hide */
interface ITalSecManager {
    /**
     * Report behavior data from apps to system server.
     */
    void reportBehavior(String json);

    /**
     * Register a listener to receive behavior data.
     * Requires permission: android.permission.READ_LOGS or similar system permission.
     */
    void registerListener(ITalSecListener listener);

    /**
     * Unregister a listener.
     */
    void unregisterListener(ITalSecListener listener);
}
