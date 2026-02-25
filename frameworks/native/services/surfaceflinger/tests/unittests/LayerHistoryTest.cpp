#undef LOG_TAG
#define LOG_TAG "LayerHistoryUnittests"

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <log/log.h>

#include <mutex>
#include <thread>

#include "Scheduler/LayerHistory.h"

using testing::_;
using testing::Return;

namespace android {
namespace scheduler {

class LayerHistoryTest : public testing::Test {
public:
    LayerHistoryTest();
    ~LayerHistoryTest() override;

protected:
    std::unique_ptr<LayerHistory> mLayerHistory;

    static constexpr float MAX_REFRESH_RATE = 90.f;
};

LayerHistoryTest::LayerHistoryTest() {
    mLayerHistory = std::make_unique<LayerHistory>();
}
LayerHistoryTest::~LayerHistoryTest() {}

namespace {
TEST_F(LayerHistoryTest, oneLayer) {
    std::unique_ptr<LayerHistory::LayerHandle> testLayer =
            mLayerHistory->createLayer("TestLayer", MAX_REFRESH_RATE);
    mLayerHistory->setVisibility(testLayer, true);

    mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    EXPECT_FLOAT_EQ(0.f, mLayerHistory->getDesiredRefreshRateAndHDR().first);

    mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    // This is still 0, because the layer is not considered recently active if it
    // has been present in less than 10 frames.
    EXPECT_FLOAT_EQ(0.f, mLayerHistory->getDesiredRefreshRateAndHDR().first);
    mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    // This should be MAX_REFRESH_RATE as we have more than 10 samples
    EXPECT_FLOAT_EQ(MAX_REFRESH_RATE, mLayerHistory->getDesiredRefreshRateAndHDR().first);
}

TEST_F(LayerHistoryTest, oneHDRLayer) {
    std::unique_ptr<LayerHistory::LayerHandle> testLayer =
            mLayerHistory->createLayer("TestHDRLayer", MAX_REFRESH_RATE);
    mLayerHistory->setVisibility(testLayer, true);

    mLayerHistory->insert(testLayer, 0, true /*isHDR*/);
    EXPECT_FLOAT_EQ(0.0f, mLayerHistory->getDesiredRefreshRateAndHDR().first);
    EXPECT_EQ(true, mLayerHistory->getDesiredRefreshRateAndHDR().second);

    mLayerHistory->setVisibility(testLayer, false);
    EXPECT_FLOAT_EQ(0.0f, mLayerHistory->getDesiredRefreshRateAndHDR().first);
    EXPECT_EQ(false, mLayerHistory->getDesiredRefreshRateAndHDR().second);
}

TEST_F(LayerHistoryTest, explicitTimestamp) {
    std::unique_ptr<LayerHistory::LayerHandle> test30FpsLayer =
            mLayerHistory->createLayer("30FpsLayer", MAX_REFRESH_RATE);
    mLayerHistory->setVisibility(test30FpsLayer, true);

    nsecs_t startTime = systemTime();
    for (int i = 0; i < 31; i++) {
        mLayerHistory->insert(test30FpsLayer, startTime + (i * 33333333), false /*isHDR*/);
    }

    EXPECT_FLOAT_EQ(30.f, mLayerHistory->getDesiredRefreshRateAndHDR().first);
}

TEST_F(LayerHistoryTest, multipleLayers) {
    std::unique_ptr<LayerHistory::LayerHandle> testLayer =
            mLayerHistory->createLayer("TestLayer", MAX_REFRESH_RATE);
    mLayerHistory->setVisibility(testLayer, true);
    std::unique_ptr<LayerHistory::LayerHandle> test30FpsLayer =
            mLayerHistory->createLayer("30FpsLayer", MAX_REFRESH_RATE);
    mLayerHistory->setVisibility(test30FpsLayer, true);
    std::unique_ptr<LayerHistory::LayerHandle> testLayer2 =
            mLayerHistory->createLayer("TestLayer2", MAX_REFRESH_RATE);
    mLayerHistory->setVisibility(testLayer2, true);

    nsecs_t startTime = systemTime();
    for (int i = 0; i < 10; i++) {
        mLayerHistory->insert(testLayer, 0, false /*isHDR*/);
    }
    EXPECT_FLOAT_EQ(MAX_REFRESH_RATE, mLayerHistory->getDesiredRefreshRateAndHDR().first);

    startTime = systemTime();
    for (int i = 0; i < 10; i++) {
        mLayerHistory->insert(test30FpsLayer, startTime + (i * 33333333), false /*isHDR*/);
    }
    EXPECT_FLOAT_EQ(MAX_REFRESH_RATE, mLayerHistory->getDesiredRefreshRateAndHDR().first);

    for (int i = 10; i < 30; i++) {
        mLayerHistory->insert(test30FpsLayer, startTime + (i * 33333333), false /*isHDR*/);
    }
    EXPECT_FLOAT_EQ(MAX_REFRESH_RATE, mLayerHistory->getDesiredRefreshRateAndHDR().first);

    // This frame is only around for 9 occurrences, so it doesn't throw
    // anything off.
    for (int i = 0; i < 9; i++) {
        mLayerHistory->insert(testLayer2, 0, false /*isHDR*/);
    }
    EXPECT_FLOAT_EQ(MAX_REFRESH_RATE, mLayerHistory->getDesiredRefreshRateAndHDR().first);
    // After 100 ms frames become obsolete.
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    // Insert the 31st frame.
    mLayerHistory->insert(test30FpsLayer, startTime + (30 * 33333333), false /*isHDR*/);
    EXPECT_FLOAT_EQ(30.f, mLayerHistory->getDesiredRefreshRateAndHDR().first);
}

} // namespace
} // namespace scheduler
} // namespace android