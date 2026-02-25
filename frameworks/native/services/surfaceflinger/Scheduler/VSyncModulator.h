/*
 * Copyright 2018 The Android Open Source Project
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

#pragma once

#include <utils/Errors.h>

#include <cinttypes>
#include <mutex>

#include "Scheduler.h"

namespace android {

/*
 * Modulates the vsync-offsets depending on current SurfaceFlinger state.
 */
class VSyncModulator {
private:
    // Number of frames we'll keep the early phase offsets once they are activated for a
    // transaction. This acts as a low-pass filter in case the client isn't quick enough in
    // sending new transactions.
    const int MIN_EARLY_FRAME_COUNT_TRANSACTION = 2;

public:
    struct Offsets {
        nsecs_t sf;
        nsecs_t app;
    };

    // Sets the phase offsets
    //
    // sfEarly: The phase offset when waking up SF early, which happens when marking a transaction
    //          as early. May be the same as late, in which case we don't shift offsets.
    // sfEarlyGl: Like sfEarly, but only if we used GL composition. If we use both GL composition
    //            and the transaction was marked as early, we'll use sfEarly.
    // sfLate: The regular SF vsync phase offset.
    // appEarly: Like sfEarly, but for the app-vsync
    // appEarlyGl: Like sfEarlyGl, but for the app-vsync.
    // appLate: The regular app vsync phase offset.
    void setPhaseOffsets(Offsets early, Offsets earlyGl, Offsets late) {
        mEarlyOffsets = early;
        mEarlyGlOffsets = earlyGl;
        mLateOffsets = late;

        if (mSfConnectionHandle && late.sf != mOffsets.load().sf) {
            mScheduler->setPhaseOffset(mSfConnectionHandle, late.sf);
        }

        if (mAppConnectionHandle && late.app != mOffsets.load().app) {
            mScheduler->setPhaseOffset(mAppConnectionHandle, late.app);
        }

        mOffsets = late;
    }

    Offsets getEarlyOffsets() const { return mEarlyOffsets; }

    Offsets getEarlyGlOffsets() const { return mEarlyGlOffsets; }

    void setEventThreads(EventThread* sfEventThread, EventThread* appEventThread) {
        mSfEventThread = sfEventThread;
        mAppEventThread = appEventThread;
    }

    void setSchedulerAndHandles(Scheduler* scheduler,
                                Scheduler::ConnectionHandle* appConnectionHandle,
                                Scheduler::ConnectionHandle* sfConnectionHandle) {
        mScheduler = scheduler;
        mAppConnectionHandle = appConnectionHandle;
        mSfConnectionHandle = sfConnectionHandle;
    }

    void setTransactionStart(Scheduler::TransactionStart transactionStart) {
        if (transactionStart == Scheduler::TransactionStart::EARLY) {
            mRemainingEarlyFrameCount = MIN_EARLY_FRAME_COUNT_TRANSACTION;
        }

        // An early transaction stays an early transaction.
        if (transactionStart == mTransactionStart ||
            mTransactionStart == Scheduler::TransactionStart::EARLY) {
            return;
        }
        mTransactionStart = transactionStart;
        updateOffsets();
    }

    void onTransactionHandled() {
        if (mTransactionStart == Scheduler::TransactionStart::NORMAL) return;
        mTransactionStart = Scheduler::TransactionStart::NORMAL;
        updateOffsets();
    }

    // Called when we send a refresh rate change to hardware composer, so that
    // we can move into early offsets.
    void onRefreshRateChangeInitiated() {
        if (mRefreshRateChangePending) {
            return;
        }
        mRefreshRateChangePending = true;
        updateOffsets();
    }

    // Called when we detect from vsync signals that the refresh rate changed.
    // This way we can move out of early offsets if no longer necessary.
    void onRefreshRateChangeDetected() {
        if (!mRefreshRateChangePending) {
            return;
        }
        mRefreshRateChangePending = false;
        updateOffsets();
    }

    void onRefreshed(bool usedRenderEngine) {
        bool updateOffsetsNeeded = false;
        if (mRemainingEarlyFrameCount > 0) {
            mRemainingEarlyFrameCount--;
            updateOffsetsNeeded = true;
        }
        if (usedRenderEngine != mLastFrameUsedRenderEngine) {
            mLastFrameUsedRenderEngine = usedRenderEngine;
            updateOffsetsNeeded = true;
        }
        if (updateOffsetsNeeded) {
            updateOffsets();
        }
    }

    Offsets getOffsets() {
        // Early offsets are used if we're in the middle of a refresh rate
        // change, or if we recently begin a transaction.
        if (mTransactionStart == Scheduler::TransactionStart::EARLY ||
            mRemainingEarlyFrameCount > 0 || mRefreshRateChangePending) {
            return mEarlyOffsets;
        } else if (mLastFrameUsedRenderEngine) {
            return mEarlyGlOffsets;
        } else {
            return mLateOffsets;
        }
    }

private:
    void updateOffsets() {
        const Offsets desired = getOffsets();
        const Offsets current = mOffsets;

        bool changed = false;
        if (desired.sf != current.sf) {
            if (mSfConnectionHandle != nullptr) {
                mScheduler->setPhaseOffset(mSfConnectionHandle, desired.sf);
            } else {
                mSfEventThread->setPhaseOffset(desired.sf);
            }
            changed = true;
        }
        if (desired.app != current.app) {
            if (mAppConnectionHandle != nullptr) {
                mScheduler->setPhaseOffset(mAppConnectionHandle, desired.app);
            } else {
                mAppEventThread->setPhaseOffset(desired.app);
            }
            changed = true;
        }

        if (changed) {
            mOffsets = desired;
        }
    }

    Offsets mLateOffsets;
    Offsets mEarlyOffsets;
    Offsets mEarlyGlOffsets;

    EventThread* mSfEventThread = nullptr;
    EventThread* mAppEventThread = nullptr;

    Scheduler* mScheduler = nullptr;
    Scheduler::ConnectionHandle* mAppConnectionHandle = nullptr;
    Scheduler::ConnectionHandle* mSfConnectionHandle = nullptr;

    std::atomic<Offsets> mOffsets;

    std::atomic<Scheduler::TransactionStart> mTransactionStart =
            Scheduler::TransactionStart::NORMAL;
    std::atomic<bool> mLastFrameUsedRenderEngine = false;
    std::atomic<bool> mRefreshRateChangePending = false;
    std::atomic<int> mRemainingEarlyFrameCount = 0;
};

} // namespace android
