/*
 * Copyright (C) 2018 The Android Open Source Project
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

package com.android.server.wifi;

import static org.junit.Assert.assertEquals;
import static org.mockito.Mockito.anyInt;
import static org.mockito.Mockito.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import android.content.Context;
import android.provider.Settings;

import androidx.test.filters.SmallTest;

import com.android.server.wifi.nano.WifiMetricsProto.WifiIsUnusableEvent;

import org.junit.Before;
import org.junit.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;

/**
 * Unit tests for {@link com.android.server.wifi.WifiDataStall}.
 */
@SmallTest
public class WifiDataStallTest {

    @Mock Context mContext;
    @Mock FrameworkFacade mFacade;
    @Mock WifiMetrics mWifiMetrics;
    WifiDataStall mWifiDataStall;

    private final WifiLinkLayerStats mOldLlStats = new WifiLinkLayerStats();
    private final WifiLinkLayerStats mNewLlStats = new WifiLinkLayerStats();

    /**
     * Sets up for unit test
     */
    @Before
    public void setUp() throws Exception {
        MockitoAnnotations.initMocks(this);
        when(mFacade.getIntegerSetting(mContext,
                Settings.Global.WIFI_DATA_STALL_MIN_TX_BAD,
                WifiDataStall.MIN_TX_BAD_DEFAULT))
                .thenReturn(WifiDataStall.MIN_TX_BAD_DEFAULT);
        when(mFacade.getIntegerSetting(mContext,
                Settings.Global.WIFI_DATA_STALL_MIN_TX_SUCCESS_WITHOUT_RX,
                WifiDataStall.MIN_TX_SUCCESS_WITHOUT_RX_DEFAULT))
                .thenReturn(WifiDataStall.MIN_TX_SUCCESS_WITHOUT_RX_DEFAULT);

        mWifiDataStall = new WifiDataStall(mContext, mFacade, mWifiMetrics);

        mOldLlStats.txmpdu_be = 1000;
        mOldLlStats.retries_be = 2000;
        mOldLlStats.lostmpdu_be = 3000;
        mOldLlStats.rxmpdu_be = 4000;
        mOldLlStats.timeStampInMs = 10000;

        mNewLlStats.txmpdu_be = mOldLlStats.txmpdu_be;
        mNewLlStats.retries_be = mOldLlStats.retries_be;
        mNewLlStats.lostmpdu_be = mOldLlStats.lostmpdu_be;
        mNewLlStats.rxmpdu_be = mOldLlStats.rxmpdu_be;
        mNewLlStats.timeStampInMs = mOldLlStats.timeStampInMs
                + WifiDataStall.MAX_MS_DELTA_FOR_DATA_STALL - 1;
    }

    /**
     * Verify that LinkLayerStats for WifiIsUnusableEvent is correctly updated
     */
    private void verifyUpdateWifiIsUnusableLinkLayerStats() {
        verify(mWifiMetrics).updateWifiIsUnusableLinkLayerStats(
                mNewLlStats.txmpdu_be - mOldLlStats.txmpdu_be,
                mNewLlStats.retries_be - mOldLlStats.retries_be,
                mNewLlStats.lostmpdu_be - mOldLlStats.lostmpdu_be,
                mNewLlStats.rxmpdu_be - mOldLlStats.rxmpdu_be,
                mNewLlStats.timeStampInMs - mOldLlStats.timeStampInMs);
    }

    /**
     * Verify there is data stall from tx failures
     */
    @Test
    public void verifyDataStallTxFailure() throws Exception {
        mNewLlStats.lostmpdu_be = mOldLlStats.lostmpdu_be + WifiDataStall.MIN_TX_BAD_DEFAULT;
        assertEquals(WifiIsUnusableEvent.TYPE_DATA_STALL_BAD_TX,
                mWifiDataStall.checkForDataStall(mOldLlStats, mNewLlStats));
        verifyUpdateWifiIsUnusableLinkLayerStats();
        verify(mWifiMetrics).logWifiIsUnusableEvent(WifiIsUnusableEvent.TYPE_DATA_STALL_BAD_TX);
    }

    /**
     * Verify there is data stall from rx failures
     */
    @Test
    public void verifyDataStallRxFailure() throws Exception {
        mNewLlStats.txmpdu_be =
                mOldLlStats.txmpdu_be + WifiDataStall.MIN_TX_SUCCESS_WITHOUT_RX_DEFAULT;
        assertEquals(WifiIsUnusableEvent.TYPE_DATA_STALL_TX_WITHOUT_RX,
                mWifiDataStall.checkForDataStall(mOldLlStats, mNewLlStats));
        verifyUpdateWifiIsUnusableLinkLayerStats();
        verify(mWifiMetrics).logWifiIsUnusableEvent(
                WifiIsUnusableEvent.TYPE_DATA_STALL_TX_WITHOUT_RX);
    }

    /**
     * Verify there is data stall from both tx and rx failures
     */
    @Test
    public void verifyDataStallBothTxRxFailure() throws Exception {
        mNewLlStats.lostmpdu_be = mOldLlStats.lostmpdu_be + WifiDataStall.MIN_TX_BAD_DEFAULT;
        mNewLlStats.txmpdu_be =
                mOldLlStats.txmpdu_be + WifiDataStall.MIN_TX_SUCCESS_WITHOUT_RX_DEFAULT;
        assertEquals(WifiIsUnusableEvent.TYPE_DATA_STALL_BOTH,
                mWifiDataStall.checkForDataStall(mOldLlStats, mNewLlStats));
        verifyUpdateWifiIsUnusableLinkLayerStats();
        verify(mWifiMetrics).logWifiIsUnusableEvent(WifiIsUnusableEvent.TYPE_DATA_STALL_BOTH);
    }

    /**
     * Verify that we can change the minimum number of tx failures
     * to trigger data stall from settings
     */
    @Test
    public void verifyDataStallTxFailureSettingsChange() throws Exception {
        when(mFacade.getIntegerSetting(mContext,
                Settings.Global.WIFI_DATA_STALL_MIN_TX_BAD,
                WifiDataStall.MIN_TX_BAD_DEFAULT))
                .thenReturn(WifiDataStall.MIN_TX_BAD_DEFAULT + 1);
        mWifiDataStall.loadSettings();
        verify(mWifiMetrics).setWifiDataStallMinTxBad(WifiDataStall.MIN_TX_BAD_DEFAULT + 1);
        verify(mWifiMetrics, times(2)).setWifiDataStallMinRxWithoutTx(
                WifiDataStall.MIN_TX_SUCCESS_WITHOUT_RX_DEFAULT);

        mNewLlStats.lostmpdu_be = mOldLlStats.lostmpdu_be + WifiDataStall.MIN_TX_BAD_DEFAULT;
        assertEquals(WifiIsUnusableEvent.TYPE_UNKNOWN,
                mWifiDataStall.checkForDataStall(mOldLlStats, mNewLlStats));
        verifyUpdateWifiIsUnusableLinkLayerStats();
        verify(mWifiMetrics, never()).logWifiIsUnusableEvent(anyInt());
    }

    /**
     * Verify that we can change the minimum number of tx successes when rx success is 0
     * to trigger data stall from settings
     */
    @Test
    public void verifyDataStallRxFailureSettingsChange() throws Exception {
        when(mFacade.getIntegerSetting(mContext,
                Settings.Global.WIFI_DATA_STALL_MIN_TX_SUCCESS_WITHOUT_RX,
                WifiDataStall.MIN_TX_SUCCESS_WITHOUT_RX_DEFAULT))
                .thenReturn(WifiDataStall.MIN_TX_SUCCESS_WITHOUT_RX_DEFAULT + 1);
        mWifiDataStall.loadSettings();
        verify(mWifiMetrics, times(2)).setWifiDataStallMinTxBad(WifiDataStall.MIN_TX_BAD_DEFAULT);
        verify(mWifiMetrics).setWifiDataStallMinRxWithoutTx(
                WifiDataStall.MIN_TX_SUCCESS_WITHOUT_RX_DEFAULT + 1);

        mNewLlStats.txmpdu_be =
                mOldLlStats.txmpdu_be + WifiDataStall.MIN_TX_SUCCESS_WITHOUT_RX_DEFAULT;
        assertEquals(WifiIsUnusableEvent.TYPE_UNKNOWN,
                mWifiDataStall.checkForDataStall(mOldLlStats, mNewLlStats));
        verifyUpdateWifiIsUnusableLinkLayerStats();
        verify(mWifiMetrics, never()).logWifiIsUnusableEvent(anyInt());
    }

    /**
     * Verify there is no data stall when there are no new tx/rx failures
     */
    @Test
    public void verifyNoDataStallWhenNoFail() throws Exception {
        assertEquals(WifiIsUnusableEvent.TYPE_UNKNOWN,
                mWifiDataStall.checkForDataStall(mOldLlStats, mNewLlStats));
        verify(mWifiMetrics, never()).resetWifiIsUnusableLinkLayerStats();
        verifyUpdateWifiIsUnusableLinkLayerStats();
        verify(mWifiMetrics, never()).logWifiIsUnusableEvent(anyInt());
    }

    /**
     * Verify there is no data stall when the time difference between
     * two WifiLinkLayerStats is too big.
     */
    @Test
    public void verifyNoDataStallBigTimeGap() throws Exception {
        mNewLlStats.lostmpdu_be = mOldLlStats.lostmpdu_be + WifiDataStall.MIN_TX_BAD_DEFAULT;
        mNewLlStats.timeStampInMs = mOldLlStats.timeStampInMs
                + WifiDataStall.MAX_MS_DELTA_FOR_DATA_STALL + 1;
        assertEquals(WifiIsUnusableEvent.TYPE_UNKNOWN,
                mWifiDataStall.checkForDataStall(mOldLlStats, mNewLlStats));
        verifyUpdateWifiIsUnusableLinkLayerStats();
        verify(mWifiMetrics, never()).logWifiIsUnusableEvent(anyInt());
    }

    /**
     * Verify that metrics get reset when there is a reset in WifiLinkLayerStats
     */
    @Test
    public void verifyReset() throws Exception {
        mNewLlStats.lostmpdu_be = mOldLlStats.lostmpdu_be - 1;
        assertEquals(WifiIsUnusableEvent.TYPE_UNKNOWN,
                mWifiDataStall.checkForDataStall(mOldLlStats, mNewLlStats));
        verify(mWifiMetrics).resetWifiIsUnusableLinkLayerStats();
        verify(mWifiMetrics, never()).updateWifiIsUnusableLinkLayerStats(
                anyLong(), anyLong(), anyLong(), anyLong(), anyLong());
        verify(mWifiMetrics, never()).logWifiIsUnusableEvent(anyInt());
    }
}
