## Codec2 VTS Hal @ 1.0 tests ##
---
#### master :
Functionality of master is to enumerate all the Codec2 components available in C2 media service.

usage: VtsHalMediaC2V1\_0TargetMasterTest -I default

#### component :
Functionality of component test is to validate common functionality across all the Codec2 components available in C2 media service. For a standard C2 component, these tests are expected to pass.

usage: VtsHalMediaC2V1\_0TargetComponentTest -I software -C <comp name>
example: VtsHalMediaC2V1\_0TargetComponentTest -I software -C c2.android.vorbis.decoder

#### audio :
Functionality of audio test is to validate audio specific functionality Codec2 components. The resource files for this test are taken from media/codec2/hidl/1.0/vts/functional/res. The path to these files on the device is required to be given for bitstream tests.

usage: VtsHalMediaC2V1\_0TargetAudioDecTest -I default -C <comp name> -P /sdcard/media/
usage: VtsHalMediaC2V1\_0TargetAudioEncTest -I software -C <comp name> -P /sdcard/media/

example: VtsHalMediaC2V1\_0TargetAudioDecTest -I software -C c2.android.flac.decoder -P /sdcard/media/
example: VtsHalMediaC2V1\_0TargetAudioEncTest -I software -C c2.android.opus.encoder -P /sdcard/media/

#### video :
Functionality of video test is to validate video specific functionality Codec2 components. The resource files for this test are taken from media/codec2/hidl/1.0/vts/functional/res. The path to these files on the device is required to be given for bitstream tests.

usage: VtsHalMediaC2V1\_0TargetVideoDecTest -I default -C <comp name> -P /sdcard/media/
usage: VtsHalMediaC2V1\_0TargetVideoEncTest -I software -C <comp name> -P /sdcard/media/

example: VtsHalMediaC2V1\_0TargetVideoDecTest -I software -C c2.android.avc.decoder -P /sdcard/media/
example: VtsHalMediaC2V1\_0TargetVideoEncTest -I software -C c2.android.vp9.encoder -P /sdcard/media/

