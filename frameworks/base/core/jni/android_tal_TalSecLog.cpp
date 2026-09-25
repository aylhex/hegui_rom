#include "jni.h"
#include <nativehelper/JNIHelp.h>
#include "art/runtime/thread.h"
#include "art/runtime/stack.h"
#include "art/runtime/art_method-inl.h"
#include <sstream>

namespace android {

class PhysicalStackVisitor : public art::StackVisitor {
public:
    PhysicalStackVisitor(art::Thread* thread) : art::StackVisitor(thread, nullptr, art::StackVisitor::StackWalkKind::kIncludeInlinedFrames), ss_() {}

    bool VisitFrame() override {
        art::ArtMethod* m = GetMethod();
        if (m == nullptr || m->IsRuntimeMethod()) {
            return true;
        }
        ss_ << m->PrettyMethod() << "\n";
        return true;
    }

    std::string GetStackStr() { return ss_.str(); }

private:
    std::stringstream ss_;
};

static jstring getNativePhysicalStackTrace(JNIEnv* env, jclass clazz) {
    art::Thread* self = art::Thread::Current();
    PhysicalStackVisitor visitor(self);
    visitor.WalkStack();
    return env->NewStringUTF(visitor.GetStackStr().c_str());
}

static const JNINativeMethod gMethods[] = {
    { "getNativePhysicalStackTrace", "()Ljava/lang/String;", (void*)getNativePhysicalStackTrace },
};

int register_android_tal_TalSecLog(JNIEnv* env) {
    return jniRegisterNativeMethods(env, "android/tal/TalSecLog", gMethods, NELEM(gMethods));
}

} // namespace android