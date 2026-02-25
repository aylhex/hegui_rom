/*
 * Copyright (C) 2016 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#define LOG_TAG "IsochronousClockModel"
//#define LOG_NDEBUG 0
#include <log/log.h>

#include <stdint.h>

#include "utility/AudioClock.h"
#include "IsochronousClockModel.h"

#define MIN_LATENESS_NANOS (10 * AAUDIO_NANOS_PER_MICROSECOND)

using namespace aaudio;

IsochronousClockModel::IsochronousClockModel()
        : mMarkerFramePosition(0)
        , mMarkerNanoTime(0)
        , mSampleRate(48000)
        , mFramesPerBurst(64)
        , mMaxLatenessInNanos(0)
        , mState(STATE_STOPPED)
{
}

IsochronousClockModel::~IsochronousClockModel() {
}

void IsochronousClockModel::setPositionAndTime(int64_t framePosition, int64_t nanoTime) {
    ALOGV("setPositionAndTime(%lld, %lld)",
          (long long) framePosition, (long long) nanoTime);
    mMarkerFramePosition = framePosition;
    mMarkerNanoTime = nanoTime;
}

void IsochronousClockModel::start(int64_t nanoTime) {
    ALOGV("start(nanos = %lld)\n", (long long) nanoTime);
    mMarkerNanoTime = nanoTime;
    mState = STATE_STARTING;
}

void IsochronousClockModel::stop(int64_t nanoTime) {
    ALOGV("stop(nanos = %lld)\n", (long long) nanoTime);
    setPositionAndTime(convertTimeToPosition(nanoTime), nanoTime);
    // TODO should we set position?
    mState = STATE_STOPPED;
}

bool IsochronousClockModel::isStarting() const {
    return mState == STATE_STARTING;
}

bool IsochronousClockModel::isRunning() const {
    return mState == STATE_RUNNING;
}

void IsochronousClockModel::processTimestamp(int64_t framePosition, int64_t nanoTime) {
//    ALOGD("processTimestamp() - framePosition = %lld at nanoTime %llu",
//         (long long)framePosition,
//         (long long)nanoTime);
    int64_t framesDelta = framePosition - mMarkerFramePosition;
    int64_t nanosDelta = nanoTime - mMarkerNanoTime;
    if (nanosDelta < 1000) {
        return;
    }

//    ALOGD("processTimestamp() - mMarkerFramePosition = %lld at mMarkerNanoTime %llu",
//         (long long)mMarkerFramePosition,
//         (long long)mMarkerNanoTime);

    int64_t expectedNanosDelta = convertDeltaPositionToTime(framesDelta);
//    ALOGD("processTimestamp() - expectedNanosDelta = %lld, nanosDelta = %llu",
//         (long long)expectedNanosDelta,
//         (long long)nanosDelta);

//    ALOGD("processTimestamp() - mSampleRate = %d", mSampleRate);
//    ALOGD("processTimestamp() - mState = %d", mState);
    switch (mState) {
    case STATE_STOPPED:
        break;
    case STATE_STARTING:
        setPositionAndTime(framePosition, nanoTime);
        mState = STATE_SYNCING;
        break;
    case STATE_SYNCING:
        // This will handle a burst of rapid transfer at the beginning.
        if (nanosDelta < expectedNanosDelta) {
            setPositionAndTime(framePosition, nanoTime);
        } else {
//            ALOGD("processTimestamp() - advance to STATE_RUNNING");
            mState = STATE_RUNNING;
        }
        break;
    case STATE_RUNNING:
        if (nanosDelta < expectedNanosDelta) {
            // Earlier than expected timestamp.
            // This data is probably more accurate so use it.
            // or we may be drifting due to a slow HW clock.
//            ALOGD("processTimestamp() - STATE_RUNNING - %d < %d micros - EARLY",
//                 (int) (nanosDelta / 1000), (int)(expectedNanosDelta / 1000));
            setPositionAndTime(framePosition, nanoTime);
        } else if (nanosDelta > (expectedNanosDelta + mMaxLatenessInNanos)) {
            // Later than expected timestamp.
//            ALOGD("processTimestamp() - STATE_RUNNING - %d > %d + %d micros - LATE",
//                 (int) (nanosDelta / 1000), (int)(expectedNanosDelta / 1000),
//                 (int) (mMaxLatenessInNanos / 1000));
            setPositionAndTime(framePosition - mFramesPerBurst,  nanoTime - mMaxLatenessInNanos);
        }
        break;
    default:
        break;
    }

//    ALOGD("processTimestamp() - mState = %d", mState);
}

void IsochronousClockModel::setSampleRate(int32_t sampleRate) {
    mSampleRate = sampleRate;
    update();
}

void IsochronousClockModel::setFramesPerBurst(int32_t framesPerBurst) {
    mFramesPerBurst = framesPerBurst;
    update();
}

void IsochronousClockModel::update() {
    int64_t nanosLate = convertDeltaPositionToTime(mFramesPerBurst); // uses mSampleRate
    mMaxLatenessInNanos = (nanosLate > MIN_LATENESS_NANOS) ? nanosLate : MIN_LATENESS_NANOS;
}

int64_t IsochronousClockModel::convertDeltaPositionToTime(int64_t framesDelta) const {
    return (AAUDIO_NANOS_PER_SECOND * framesDelta) / mSampleRate;
}

int64_t IsochronousClockModel::convertDeltaTimeToPosition(int64_t nanosDelta) const {
    return (mSampleRate * nanosDelta) / AAUDIO_NANOS_PER_SECOND;
}

int64_t IsochronousClockModel::convertPositionToTime(int64_t framePosition) const {
    if (mState == STATE_STOPPED) {
        return mMarkerNanoTime;
    }
    int64_t nextBurstIndex = (framePosition + mFramesPerBurst - 1) / mFramesPerBurst;
    int64_t nextBurstPosition = mFramesPerBurst * nextBurstIndex;
    int64_t framesDelta = nextBurstPosition - mMarkerFramePosition;
    int64_t nanosDelta = convertDeltaPositionToTime(framesDelta);
    int64_t time = mMarkerNanoTime + nanosDelta;
//    ALOGD("convertPositionToTime: pos = %llu --> time = %llu",
//         (unsigned long long)framePosition,
//         (unsigned long long)time);
    return time;
}

int64_t IsochronousClockModel::convertTimeToPosition(int64_t nanoTime) const {
    if (mState == STATE_STOPPED) {
        return mMarkerFramePosition;
    }
    int64_t nanosDelta = nanoTime - mMarkerNanoTime;
    int64_t framesDelta = convertDeltaTimeToPosition(nanosDelta);
    int64_t nextBurstPosition = mMarkerFramePosition + framesDelta;
    int64_t nextBurstIndex = nextBurstPosition / mFramesPerBurst;
    int64_t position = nextBurstIndex * mFramesPerBurst;
//    ALOGD("convertTimeToPosition: time = %llu --> pos = %llu",
//         (unsigned long long)nanoTime,
//         (unsigned long long)position);
//    ALOGD("convertTimeToPosition: framesDelta = %llu, mFramesPerBurst = %d",
//         (long long) framesDelta, mFramesPerBurst);
    return position;
}

void IsochronousClockModel::dump() const {
    ALOGD("mMarkerFramePosition = %lld", (long long) mMarkerFramePosition);
    ALOGD("mMarkerNanoTime      = %lld", (long long) mMarkerNanoTime);
    ALOGD("mSampleRate          = %6d", mSampleRate);
    ALOGD("mFramesPerBurst      = %6d", mFramesPerBurst);
    ALOGD("mMaxLatenessInNanos  = %6d", mMaxLatenessInNanos);
    ALOGD("mState               = %6d", mState);
}
