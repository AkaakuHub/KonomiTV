<template>
    <div class="route-container">
        <HeaderBar />
        <main>
            <Navigation />
            <div class="conditions-page">
                <SPHeaderBar />
                <div class="conditions-page__content">
                    <Breadcrumbs :crumbs="[
                        { name: 'ホーム', path: '/' },
                        { name: '録画予約', path: '/reservations/' },
                        { name: 'キーワード自動予約', path: '/reservations/conditions', disabled: true },
                    ]" />
                    <div class="conditions-page__heading">
                        <h2>キーワード自動予約</h2>
                        <v-btn v-if="isMirakcBackend" color="primary" @click="openEditor(null)">条件を追加</v-btn>
                    </div>
                    <p v-if="!isMirakcBackend">この画面はmirakcバックエンドで利用できます。</p>
                    <template v-else>
                        <v-progress-linear v-if="isLoading" indeterminate color="primary" />
                        <p v-else-if="loadFailed">条件一覧を取得できませんでした。</p>
                        <p v-else-if="conditions.length === 0">条件を追加すると、番組表に一致する番組を自動で予約します。</p>
                        <v-card v-for="condition in conditions" :key="condition.id" class="conditions-page__condition" variant="outlined">
                            <div class="conditions-page__heading">
                                <h3>{{ condition.program_search_condition.note || condition.program_search_condition.keyword || 'キーワード指定なし' }}</h3>
                                <v-chip size="small" :color="condition.program_search_condition.is_enabled ? 'primary' : undefined">
                                    {{ condition.program_search_condition.is_enabled ? '有効' : '無効' }}
                                </v-chip>
                            </div>
                            <p>予約中：{{ condition.reservation_count }}件</p>
                            <v-card-actions>
                                <v-btn :disabled="busyId === condition.id" @click="toggleCondition(condition)">
                                    {{ condition.program_search_condition.is_enabled ? '無効にする' : '有効にする' }}
                                </v-btn>
                                <v-btn :disabled="busyId === condition.id" @click="openEditor(condition)">編集</v-btn>
                                <v-spacer />
                                <v-btn color="error" :disabled="busyId === condition.id" @click="deletingCondition = condition">削除</v-btn>
                            </v-card-actions>
                        </v-card>
                        <v-btn class="mt-4" variant="text" :loading="isLoading" @click="loadConditions">更新</v-btn>
                    </template>
                </div>
            </div>
        </main>
        <v-dialog v-model="isEditorOpen" max-width="1100" scrollable persistent>
            <ReservationConditionEditor v-if="isEditorOpen" :condition="editingCondition" :channels="allChannels"
                @close="isEditorOpen = false" @saved="handleSaved" />
        </v-dialog>
        <v-dialog :model-value="deletingCondition !== null" max-width="480" persistent>
            <v-card title="自動予約条件を削除">
                <v-card-text>この条件を削除します。登録済みの録画予約は残ります。</v-card-text>
                <v-card-actions>
                    <v-spacer />
                    <v-btn :disabled="busyId !== null" @click="deletingCondition = null">キャンセル</v-btn>
                    <v-btn color="error" :loading="busyId !== null" @click="deleteCondition">削除</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </div>
</template>
<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';

import Breadcrumbs from '@/components/Breadcrumbs.vue';
import HeaderBar from '@/components/HeaderBar.vue';
import Navigation from '@/components/Navigation.vue';
import ReservationConditionEditor from '@/components/Reservations/ReservationConditionEditor.vue';
import SPHeaderBar from '@/components/SPHeaderBar.vue';
import ReservationConditions, { IReservationCondition } from '@/services/ReservationConditions';
import useChannelsStore from '@/stores/ChannelsStore';
import useServerSettingsStore from '@/stores/ServerSettingsStore';

const channelsStore = useChannelsStore();
const serverSettingsStore = useServerSettingsStore();
const isMirakcBackend = computed(() => serverSettingsStore.server_settings.general.backend === 'Mirakc');
const allChannels = computed(() => Object.values(channelsStore.channels_list).flat());
const conditions = ref<IReservationCondition[]>([]);
const isLoading = ref(false);
const loadFailed = ref(false);
const isEditorOpen = ref(false);
const editingCondition = ref<IReservationCondition | null>(null);
const deletingCondition = ref<IReservationCondition | null>(null);
const busyId = ref<number | null>(null);
let refreshInterval: ReturnType<typeof setInterval> | null = null;

const loadConditions = async () => {
    if (!isMirakcBackend.value || isLoading.value) return;
    isLoading.value = true;
    try {
        const result = await ReservationConditions.fetchReservationConditions();
        loadFailed.value = result === null;
        if (result !== null) conditions.value = result.reservation_conditions;
    } finally {
        isLoading.value = false;
    }
};
const openEditor = (condition: IReservationCondition | null) => {
    editingCondition.value = condition;
    isEditorOpen.value = true;
};
const handleSaved = async () => {
    isEditorOpen.value = false;
    await loadConditions();
};
const toggleCondition = async (condition: IReservationCondition) => {
    busyId.value = condition.id;
    try {
        const result = await ReservationConditions.updateReservationCondition(condition.id, {
            ...condition.program_search_condition, is_enabled: !condition.program_search_condition.is_enabled,
        }, condition.record_settings);
        if (result !== null) await loadConditions();
    } finally {
        busyId.value = null;
    }
};
const deleteCondition = async () => {
    if (deletingCondition.value === null) return;
    busyId.value = deletingCondition.value.id;
    try {
        if (await ReservationConditions.deleteReservationCondition(deletingCondition.value.id)) {
            deletingCondition.value = null;
            await loadConditions();
        }
    } finally {
        busyId.value = null;
    }
};
onMounted(async () => {
    await Promise.all([channelsStore.update(), serverSettingsStore.fetchServerSettingsOnce()]);
    await loadConditions();
    refreshInterval = setInterval(loadConditions, 30_000);
});
onUnmounted(() => {
    if (refreshInterval !== null) clearInterval(refreshInterval);
});
</script>
<style lang="scss" scoped>
.conditions-page {
    width: 100%;
    min-width: 0;

    &__content {
        max-width: 1000px;
        margin: 0 auto;
        padding: 20px;

        @include smartphone-vertical { padding: 8px; }
    }

    &__heading {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 12px;
        margin-bottom: 16px;
        h3 { overflow-wrap: anywhere; }
    }

    &__condition {
        padding: 16px;
        margin-top: 16px;
    }
}
</style>
