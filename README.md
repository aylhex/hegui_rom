# Android App隐私合规检测定制系统

## 简介

市面上的大部分的合规检测工具是使用Frida或Xposed等Hook框架进行Hook注入代码，通常会带来额外的性能开销，包括更高的延迟和资源消耗，Hook过程中的错误或与应用的不兼容可能导致应用崩溃或不稳定。直接修改AOSP源码能够实现对操作系统所有层级（包括内核、系统服务、框架等）的深度控制和集成，实现从底层到应用层的全面隐私合规检测，系统的稳定性和可靠性相对较高，不会因运行时的动态代码注入带来不确定性的问题。

## 检测项

基于Android-10.0.0_r2版本源码进行的修改，并编译了适配Pixel 2 XL机型的镜像，具体改动位置和检测点如下表所示：

| **序号** | **文件所在路径**                                                                | **监测内容**     | **目标函数**                                                  |
| ------ | ------------------------------------------------------------------------- | ------------ | --------------------------------------------------------- |
| **1**  | frameworks/base/core/java/android/app/ApplicationPackageManager.java      | 权限申请         | int checkPermission(String permName, String pkgName)                                           |
| **2**  | frameworks/base/core/java/android/app/ApplicationPackageManager.java      | 获取APP安装列表    | List<PackageInfo> getInstalledPackages(int flags)         |
| **3**  | frameworks/base/core/java/android/app/ApplicationPackageManager.java      | 获取APP安装列表    | List<ApplicationInfo> getInstalledApplications(int flags) |
| **4**  | frameworks/base/core/java/android/app/ActivityManager.java                | 正在运行的进程      | List<RunningAppProcessInfo> getRunningAppProcesses()                                    |
| **5**  | frameworks/base/core/java/android/app/ActivityManager.java                | 正在运行的服务      | PendingIntent getRunningServiceControlPanel(ComponentName service)                             |
| **6**  | frameworks/base/core/java/android/app/admin/DevicePolicyManager.java      | 获取Mac地址      | String getWifiMacAddress(ComponentName admin)                    |
| **7**  | frameworks/base/core/java/android/bluetooth/BluetoothAdapter.java         | 获取蓝牙名称       | String getName()                                                |
| **8**  | frameworks/base/core/java/android/bluetooth/BluetoothDevice.java           | 获取蓝牙Mac地址    | String getAddress()                                              |
| **9**  | frameworks/base/core/java/android/bluetooth/BluetoothDevice.java          | 获取蓝牙名称       | String getName()                                               |
| **10** | frameworks/base/core/java/android/content/ClipboardManager.java           | 获取剪切板信息      | void setPrimaryClip(ClipData clip)                                           |
| **11** | frameworks/base/core/java/android/content/ClipboardManager.java           | 监测剪切板信息      | boolean hasPrimaryClip()                                          |
| **12** | frameworks/base/core/java/android/content/ClipboardManager.java           | 设置剪切板信息      | void setPrimaryClip(ClipData clip)                                            |
| **13** | frameworks/base/core/java/android/content/Camera.java                     | 打开摄像头        | Camera open(int cameraId)                                 |
| **14** | frameworks/base/core/java/android/hardware/camera2/CameraManager.java     | 打开摄像头        | openCameraDeviceUserAsync                                 |
| **15** | frameworks/base/core/java/android/hardware/SensorManager.java             | 获取传感器信息      | List<Sensor> getSensorList(int type)                      |
| **16** | frameworks/base/core/java/android/os/Build.java                           | 获取设备序列号      | String getSerial()                                        |
| **17** | frameworks/base/core/java/android/provider/Settings.java                  | 获取Android_id | String getString(ContentResolver resolver, String name)   |
| **18** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 获取IMEI       | String getDeviceId()                                      |
| **19** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 获取IMEI       | String getImei(int slotIndex)                             |
| **20** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 获取MEID       | String getMeid(int slotIndex)                             |
| **21** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 获取MCC/MNC    | String getNetworkOperatorName(int subId)                  |
| **22** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 获取当前位置信息     | CellLocation getCellLocation()                            |
| **23** | frameworks/base/location/java/android/location/Location.java              | 获取纬度信息       | double getLatitude()                                      |
| **24** | frameworks/base/location/java/android/location/Location.java              | 获取经度信息       | double getLongitude()                                     |
| **25** | frameworks/base/location/java/android/location/LocationManager.java       | 获取最后已知位置     | Location getLastKnownLocation(@NonNull String provider)   |
| **26** | frameworks/base/location/java/android/location/LocationManager.java       | 获取最后已知位置     | Location getLastLocation()                                |
| **27** | frameworks/base/telephony/java/android/telephony/gsm/GsmCellLocation.java | 获取基站cid信息    | int getCid()                                              |
| **28** | frameworks/base/telephony/java/android/telephony/gsm/GsmCellLocation.java | 获取基站lac信息    | int getLac()                                              |
| **29** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 获取SIM卡国际代码   | String getSimCountryIsoForPhone(int phoneId)              |
| **30** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 获取IMSI/ICCID | String getSimSerialNumber(int subId)                      |
| **31** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 获取IMSI       | String getSubscriberId(int subId)                         |
| **32** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 获取电话号码       | String getLine1Number(int subId)                          |
| **33** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 获取IMSI       | int getSubscriptionId()                                   |
| **34** | frameworks/base/core/java/android/telephony/TelephonyManager.java         | 检测sim卡是否可用   | ServiceState getServiceStateForSubscriber(int subId)      |
| **35** | frameworks/base/core/java/android/os/SystemProperties.java                | 获取系统属性       | String get(@NonNull String key)                           |
| **36** | frameworks/base/core/java/android/os/SystemProperties.java                | 设置系统属性       | void set(@NonNull String key, @Nullable String val)       |
| **37** | frameworks/base/wifi/java/android/net/wifi/WifiInfo.java                  | 获取附近Wifi列表   | List<ScanResult> getScanResults()                         |
| **38** | frameworks/base/wifi/java/android/net/wifi/WifiInfo.java                  | 获取Mac地址      | String[] getFactoryMacAddresses()                         |

## 安装

需要准备一台谷歌Pixel 2 XL型号的手机，下载提供的镜像进行刷机即可。

```shell
# 进入到bootloader模式
adb reboot bootloader

# 设置环境变量，下载的镜像存储路径
export ANDROID_PRODUCT_OUT='/Users/xxxx/xxx/taimen_rom'

# 刷机
fastboot flashall -w

# 如果刷机过程中，提示存储空间不够，可以指定刷机文件系统分区大小
fastboot flashall -S 50M -w

```

## 用法
直接打开系统中集成的”合规检测APP“ ，按着下图中的流程进行操作即可开始检测
 ![](https://github.com/aylhex/hegui_rom/blob/main/aosp_rom/hegui.png)
保证电脑和手机处于同一局域网下，即手机和电脑连接同一个wifi，在电脑的浏览器中输入APP中网址：`http://192.168.xxx.xxx:8080/`，即可看到检测结果
 ![](https://github.com/aylhex/hegui_rom/blob/main/aosp_rom/loginfo.png)
点击详情，即可查看具体的调用堆栈
 ![](https://github.com/aylhex/hegui_rom/blob/main/aosp_rom/callstack.png)
## 后续
计划会增加第三方SDK的识别和检测，同时增加更多功能比如采集频率的统计和新检测点，比如：模拟OAID的获取。(因为不是专职搞这个，更新频率可能会有点慢)


