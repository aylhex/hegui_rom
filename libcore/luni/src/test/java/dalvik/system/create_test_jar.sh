#!/bin/bash
set -e

# Create the child JAR
# --------------------------------------
rm -rf /tmp/delegate_last_child
mkdir -p /tmp/delegate_last_child/libcore/test/delegatelast;
pushd /tmp/delegate_last_child
echo "package libcore.test.delegatelast;\
      public class A {\
          public String toString() {\
              return \"A_child\";\
          }\
      }" > libcore/test/delegatelast/A.java
echo "package libcore.test.delegatelast;\
      public class Child {\
          public String toString() {\
              return \"Child_child\";\
          }\
      }" > libcore/test/delegatelast/Child.java
javac libcore/test/delegatelast/*.java

d8 --output . libcore/test/delegatelast/*.class # Creates ./classes.dex
echo -ne "child" > ./resource.txt
jar cf ./child.jar classes.dex resource.txt
cp ./child.jar $ANDROID_BUILD_TOP/libcore/luni/src/test/resources/dalvik/system/child.jar
popd

# Create the parent JAR
# --------------------------------------
rm -rf /tmp/delegate_last_parent
mkdir -p /tmp/delegate_last_parent/libcore/test/delegatelast;
pushd /tmp/delegate_last_parent
echo "package libcore.test.delegatelast;\
      public class A {\
          public String toString() {\
              return \"A_parent\";\
          }\
      }" > libcore/test/delegatelast/A.java
echo "package libcore.test.delegatelast;\
      public class Parent {\
          public String toString() {\
              return \"Parent_parent\";\
          }\
      }" > libcore/test/delegatelast/Parent.java
javac libcore/test/delegatelast/*.java
d8 --output . libcore/test/delegatelast/*.class # Creates ./classes.dex
echo -ne "parent" > ./resource.txt
echo -ne "parent2" > ./resource2.txt
jar cf ./parent.jar classes.dex resource.txt resource2.txt
cp ./parent.jar $ANDROID_BUILD_TOP/libcore/luni/src/test/resources/dalvik/system/parent.jar
popd


# Create a jar that overloads boot classpath classes and resources
# ----------------------------------------------------------------
rm -rf /tmp/delegate_last_bootoverride
mkdir -p /tmp/delegate_last_bootoverride/java/util;
pushd /tmp/delegate_last_bootoverride
echo "package java.util;\
      public class HashMap {\
          public String toString() {\
              return \"I'm not really a HashMap\";\
          }\
      }" > java/util/HashMap.java
javac --patch-module=java.base=. java/util/HashMap.java
d8 --output . java/util/HashMap.class # Creates ./classes.dex
mkdir -p android/icu
echo -ne "NOT ICU" > android/icu/ICUConfig.properties
jar cf ./bootoverride.jar classes.dex android/icu/ICUConfig.properties
cp ./bootoverride.jar $ANDROID_BUILD_TOP/libcore/luni/src/test/resources/dalvik/system/bootoverride.jar
popd
