package frameworks.base.core.java.tal.ayl;

import android.content.ContentResolver;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.RemoteException;
import android.util.Log;
import tal.ayl.IMKOService;

//https://david1840.github.io/2020/08/07/Android-%E6%B7%BB%E5%8A%A0%E8%87%AA%E5%AE%9A%E4%B9%89%E7%B3%BB%E7%BB%9F%E6%9C%8D%E5%8A%A1/
//https://www.jianshu.com/p/74971ee85a8b
public class MKOService extends IMKOService.Stub{

    private Context mContext;

    public MKOService(Context context){
        mContext = context;
        Log.v("TAL ", "MKOService is init");
    }

    @Override
    public String queryWatchPackage(String key)  throws RemoteException  {

        String value = "";
        try {
            ContentResolver contentResolver = mContext.getContentResolver();
            String[] projection = {"value"};
            String selection = "key = ?";
            String[] selectionArgs = {key};

            try (Cursor cursor = contentResolver.query(
                    Uri.parse("content://com.tal.complianceprovider/data"),
                    projection,
                    selection,
                    selectionArgs,
                    null)) {

                if (cursor != null && cursor.moveToFirst()) {
                    int columnIndex = cursor.getColumnIndex("value");
                    if (columnIndex != -1) {
                        value = cursor.getString(columnIndex);
                    }
                }
            }
            return value;
        } catch (Exception e) {
            e.printStackTrace();
        }
        return value;
    }

    @Override
    public String setWatchPackage(String packageName) throws RemoteException {
        return packageName;
    }
}
