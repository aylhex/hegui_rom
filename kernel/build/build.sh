#!/bin/bash

# Copyright (C) 2019 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Usage:
#   build/build.sh <make options>*
# or:
#   OUT_DIR=<out dir> DIST_DIR=<dist dir> build/build.sh <make options>*
#
# Example:
#   OUT_DIR=output DIST_DIR=dist build/build.sh -j24
#
#
# The following environment variables are considered during execution:
#
#   BUILD_CONFIG
#     Build config file to initialize the build environment from. The location
#     is to be defined relative to the repo root directory.
#     Defaults to 'build.config'.
#
#   OUT_DIR
#     Base output directory for the kernel build.
#     Defaults to <REPO_ROOT>/out/<BRANCH>.
#
#   DIST_DIR
#     Base output directory for the kernel distribution.
#     Defaults to <OUT_DIR>/dist
#
#   EXT_MODULES
#     Space separated list of external kernel modules to be build.
#
#   UNSTRIPPED_MODULES
#     Space separated list of modules to be copied to <DIST_DIR>/unstripped
#     for debugging purposes.
#
#   CC
#     Override compiler to be used. (e.g. CC=clang) Specifying CC=gcc
#     effectively unsets CC to fall back to the default gcc detected by kbuild
#     (including any target triplet). To use a custom 'gcc' from PATH, use an
#     absolute path, e.g.  CC=/usr/local/bin/gcc
#
#   LD
#     Override linker (flags) to be used.
#
# Environment variables to influence the stages of the kernel build.
#
#   SKIP_MRPROPER
#     if defined, skip `make mrproper`
#
#   SKIP_DEFCONFIG
#     if defined, skip `make defconfig`
#
#   PRE_DEFCONFIG_CMDS
#     Command evaluated before `make defconfig`
#
#   POST_DEFCONFIG_CMDS
#     Command evaluated after `make defconfig` and before `make`.
#
#   POST_KERNEL_BUILD_CMDS
#     Command evaluated after `make`.
#
#   IN_KERNEL_MODULES
#     if defined, install kernel modules
#
#   SKIP_EXT_MODULES
#     if defined, skip building and installing of external modules
#
#   EXTRA_CMDS
#     Command evaluated after building and installing kernel and modules.
#
#   SKIP_CP_KERNEL_HDR
#     if defined, skip installing kernel headers.
#
# Note: For historic reasons, internally, OUT_DIR will be copied into
# COMMON_OUT_DIR, and OUT_DIR will be then set to
# ${COMMON_OUT_DIR}/${KERNEL_DIR}. This has been done to accommodate existing
# build.config files that expect ${OUT_DIR} to point to the output directory of
# the kernel build.
#
# The kernel is built in ${COMMON_OUT_DIR}/${KERNEL_DIR}.
# Out-of-tree modules are built in ${COMMON_OUT_DIR}/${EXT_MOD} where
# ${EXT_MOD} is the path to the module source code.

set -e

# rel_path <to> <from>
# Generate relative directory path to reach directory <to> from <from>
function rel_path() {
	local to=$1
	local from=$2
	local path=
	local stem=
	local prevstem=
	[ -n "$to" ] || return 1
	[ -n "$from" ] || return 1
	to=$(readlink -e "$to")
	from=$(readlink -e "$from")
	[ -n "$to" ] || return 1
	[ -n "$from" ] || return 1
	stem=${from}/
	while [ "${to#$stem}" == "${to}" -a "${stem}" != "${prevstem}" ]; do
		prevstem=$stem
		stem=$(readlink -e "${stem}/..")
		[ "${stem%/}" == "${stem}" ] && stem=${stem}/
		path=${path}../
	done
	echo ${path}${to#$stem}
}

export ROOT_DIR=$(readlink -f $(dirname $0)/..)

# For module file Signing with the kernel (if needed)
FILE_SIGN_BIN=scripts/sign-file
SIGN_SEC=certs/signing_key.pem
SIGN_CERT=certs/signing_key.x509
SIGN_ALGO=sha512

source "${ROOT_DIR}/build/envsetup.sh"

export MAKE_ARGS=$@
export MODULES_STAGING_DIR=$(readlink -m ${COMMON_OUT_DIR}/staging)
export MODULES_PRIVATE_DIR=$(readlink -m ${COMMON_OUT_DIR}/private)
export UNSTRIPPED_DIR=${DIST_DIR}/unstripped
export KERNEL_UAPI_HEADERS_DIR=$(readlink -m ${COMMON_OUT_DIR}/kernel_uapi_headers)

cd ${ROOT_DIR}

export CLANG_TRIPLE CROSS_COMPILE CROSS_COMPILE_ARM32 ARCH SUBARCH

# CC=gcc is effectively a fallback to the default gcc including any target
# triplets. If the user wants to use a custom compiler, they are still able to
# pass an absolute path, e.g. CC=/usr/bin/gcc.
[ "${CC}" == "gcc" ] && unset CC

if [ -n "${CC}" ]; then
  CC_ARG="CC=${CC}"
fi

if [ -n "${LD}" ]; then
  LD_ARG="LD=${LD}"
fi

CC_LD_ARG="${CC_ARG} ${LD_ARG}"

mkdir -p ${OUT_DIR}
echo "========================================================"
echo " Setting up for build"
if [ -z "${SKIP_MRPROPER}" ] ; then
  set -x
  (cd ${KERNEL_DIR} && make ${CC_LD_ARG} O=${OUT_DIR} mrproper)
  set +x
fi

if [ "${PRE_DEFCONFIG_CMDS}" != "" ]; then
  echo "========================================================"
  echo " Running pre-defconfig command(s):"
  set -x
  eval ${PRE_DEFCONFIG_CMDS}
  set +x
fi

if [ -z "${SKIP_DEFCONFIG}" ] ; then
set -x
(cd ${KERNEL_DIR} && make ${CC_LD_ARG} O=${OUT_DIR} ${DEFCONFIG})
set +x

if [ "${POST_DEFCONFIG_CMDS}" != "" ]; then
  echo "========================================================"
  echo " Running pre-make command(s):"
  set -x
  eval ${POST_DEFCONFIG_CMDS}
  set +x
fi
fi

echo "========================================================"
echo " Building kernel"

set -x
(cd ${OUT_DIR} && \
 make O=${OUT_DIR} ${CC_LD_ARG} -j$(nproc) $@)
set +x

if [ "${POST_KERNEL_BUILD_CMDS}" != "" ]; then
  echo "========================================================"
  echo " Running post-kernel-build command(s):"
  set -x
  eval ${POST_KERNEL_BUILD_CMDS}
  set +x
fi

rm -rf ${MODULES_STAGING_DIR}
mkdir -p ${MODULES_STAGING_DIR}

if [ -n "${IN_KERNEL_MODULES}" ]; then
  echo "========================================================"
  echo " Installing kernel modules into staging directory"

  (cd ${OUT_DIR} && \
   make O=${OUT_DIR} ${CC_LD_ARG} INSTALL_MOD_STRIP=1 \
        INSTALL_MOD_PATH=${MODULES_STAGING_DIR} modules_install)
fi

if [[ -z "${SKIP_EXT_MODULES}" ]] && [[ "${EXT_MODULES}" != "" ]]; then
  echo "========================================================"
  echo " Building external modules and installing them into staging directory"

  for EXT_MOD in ${EXT_MODULES}; do
    # The path that we pass in via the variable M needs to be a relative path
    # relative to the kernel source directory. The source files will then be
    # looked for in ${KERNEL_DIR}/${EXT_MOD_REL} and the object files (i.e. .o
    # and .ko) files will be stored in ${OUT_DIR}/${EXT_MOD_REL}. If we
    # instead set M to an absolute path, then object (i.e. .o and .ko) files
    # are stored in the module source directory which is not what we want.
    EXT_MOD_REL=$(rel_path ${ROOT_DIR}/${EXT_MOD} ${KERNEL_DIR})
    # The output directory must exist before we invoke make. Otherwise, the
    # build system behaves horribly wrong.
    mkdir -p ${OUT_DIR}/${EXT_MOD_REL}
    set -x
    make -C ${EXT_MOD} M=${EXT_MOD_REL} KERNEL_SRC=${ROOT_DIR}/${KERNEL_DIR}  \
                       O=${OUT_DIR} ${CC_LD_ARG} -j$(nproc) "$@"
    make -C ${EXT_MOD} M=${EXT_MOD_REL} KERNEL_SRC=${ROOT_DIR}/${KERNEL_DIR}  \
                       O=${OUT_DIR} ${CC_LD_ARG} INSTALL_MOD_STRIP=1   \
                       INSTALL_MOD_PATH=${MODULES_STAGING_DIR} modules_install
    set +x
  done

fi

if [ "${EXTRA_CMDS}" != "" ]; then
  echo "========================================================"
  echo " Running extra build command(s):"
  set -x
  eval ${EXTRA_CMDS}
  set +x
fi

OVERLAYS_OUT=""
for ODM_DIR in ${ODM_DIRS}; do
  OVERLAY_DIR=${ROOT_DIR}/device/${ODM_DIR}/overlays

  if [ -d ${OVERLAY_DIR} ]; then
    OVERLAY_OUT_DIR=${OUT_DIR}/overlays/${ODM_DIR}
    mkdir -p ${OVERLAY_OUT_DIR}
    make -C ${OVERLAY_DIR} DTC=${OUT_DIR}/scripts/dtc/dtc OUT_DIR=${OVERLAY_OUT_DIR}
    OVERLAYS=$(find ${OVERLAY_OUT_DIR} -name "*.dtbo")
    OVERLAYS_OUT="$OVERLAYS_OUT $OVERLAYS"
  fi
done

mkdir -p ${DIST_DIR}
echo "========================================================"
echo " Copying files"
for FILE in ${FILES}; do
  if [ -f ${OUT_DIR}/${FILE} ]; then
    echo "  $FILE"
    cp -p ${OUT_DIR}/${FILE} ${DIST_DIR}/
  else
    echo "  $FILE does not exist, skipping"
  fi
done

for FILE in ${OVERLAYS_OUT}; do
  OVERLAY_DIST_DIR=${DIST_DIR}/$(dirname ${FILE#${OUT_DIR}/overlays/})
  echo "  ${FILE#${OUT_DIR}/}"
  mkdir -p ${OVERLAY_DIST_DIR}
  cp ${FILE} ${OVERLAY_DIST_DIR}/
done

MODULES=$(find ${MODULES_STAGING_DIR} -type f -name "*.ko")
if [ -n "${MODULES}" ]; then
  echo "========================================================"
  echo " Copying modules files"
  if [ -n "${IN_KERNEL_MODULES}" -o "${EXT_MODULES}" != "" ]; then
    for FILE in ${MODULES}; do
      echo "  ${FILE#${MODULES_STAGING_DIR}/}"
      cp -p ${FILE} ${DIST_DIR}
    done
  fi
fi

if [ "${UNSTRIPPED_MODULES}" != "" ]; then
  echo "========================================================"
  echo " Copying unstripped module files for debugging purposes (not loaded on device)"
  mkdir -p ${UNSTRIPPED_DIR}
  for MODULE in ${UNSTRIPPED_MODULES}; do
    find ${MODULES_PRIVATE_DIR} -name ${MODULE} -exec cp {} ${UNSTRIPPED_DIR} \;
  done
fi

if [ -z "${SKIP_CP_KERNEL_HDR}" ]; then
  echo "========================================================"
  echo " Installing UAPI kernel headers:"
  mkdir -p "${KERNEL_UAPI_HEADERS_DIR}/usr"
  make -C ${OUT_DIR} O=${OUT_DIR} ${CC_LD_ARG} INSTALL_HDR_PATH="${KERNEL_UAPI_HEADERS_DIR}/usr" -j$(nproc) headers_install
  # The kernel makefiles create files named ..install.cmd and .install which
  # are only side products. We don't want those. Let's delete them.
  find ${KERNEL_UAPI_HEADERS_DIR} \( -name ..install.cmd -o -name .install \) -exec rm '{}' +
  KERNEL_UAPI_HEADERS_TAR=${DIST_DIR}/kernel-uapi-headers.tar.gz
  echo " Copying kernel UAPI headers to ${KERNEL_UAPI_HEADERS_TAR}"
  tar -czf ${KERNEL_UAPI_HEADERS_TAR} --directory=${KERNEL_UAPI_HEADERS_DIR} usr/
fi

if [ -z "${SKIP_CP_KERNEL_HDR}" ] ; then
	echo "========================================================"
	KERNEL_HEADERS_TAR=${DIST_DIR}/kernel-headers.tar.gz
	echo " Copying kernel headers to ${KERNEL_HEADERS_TAR}"
	TMP_DIR="${OUT_DIR}/tmp"
	TMP_KERNEL_HEADERS_CHILD="kernel-headers"
	TMP_KERNEL_HEADERS_DIR=$TMP_DIR/$TMP_KERNEL_HEADERS_CHILD
	CURDIR=$(pwd)
	mkdir -p $TMP_KERNEL_HEADERS_DIR
	cd $ROOT_DIR/$KERNEL_DIR; find arch -name *.h -exec cp --parents {} $TMP_KERNEL_HEADERS_DIR \;
	cd $ROOT_DIR/$KERNEL_DIR; find include -name *.h -exec cp --parents {} $TMP_KERNEL_HEADERS_DIR \;
	cd $OUT_DIR; find  -name *.h -exec cp --parents {} $TMP_KERNEL_HEADERS_DIR \;
	tar -czvf $KERNEL_HEADERS_TAR --directory=$TMP_DIR $TMP_KERNEL_HEADERS_CHILD > /dev/null 2>&1
	rm -rf $TMP_KERNEL_HEADERS_DIR
	cd $CURDIR
fi

echo "========================================================"
echo " Files copied to ${DIST_DIR}"

# No trace_printk use on build server build
if readelf -a ${DIST_DIR}/vmlinux 2>&1 | grep -q trace_printk_fmt; then
  echo "========================================================"
  echo "WARN: Found trace_printk usage in vmlinux."
  echo ""
  echo "trace_printk will cause trace_printk_init_buffers executed in kernel"
  echo "start, which will increase memory and lead warning shown during boot."
  echo "We should not carry trace_printk in production kernel."
  echo ""
  if [ ! -z "${STOP_SHIP_TRACEPRINTK}" ]; then
    echo "ERROR: stop ship on trace_printk usage." 1>&2
    exit 1
  fi
fi
