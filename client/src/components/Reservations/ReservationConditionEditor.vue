<template>
    <v-card class="condition-editor">
        <v-card-title>{{ condition === null ? 'キーワード自動予約を追加' : 'キーワード自動予約を編集' }}</v-card-title>
        <v-card-text>
            <div class="condition-editor__columns">
                <ProgramSearchFilters v-model:condition="searchCondition" :channels="channels"
                    :is-searching="isSearching" @search="preview" />
                <div class="condition-editor__settings">
                    <v-switch v-model="searchCondition.is_enabled" label="この条件で自動予約する" color="primary" hide-details />
                    <v-text-field v-model="searchCondition.note" label="メモ" variant="outlined" density="compact" hide-details />
                    <v-select v-model="recordSettings.priority" :items="priorityOptions" label="録画優先度"
                        variant="outlined" density="compact" hide-details />
                    <v-select v-model="recordSettings.preferred_tuner_name" :items="tunerOptions" label="優先チューナー"
                        variant="outlined" density="compact" hide-details :disabled="tuners === null" />
                    <v-select v-model="searchCondition.duplicate_title_check_scope" :items="duplicateOptions"
                        label="同名の録画済み番組" variant="outlined" density="compact" hide-details />
                    <v-text-field v-if="searchCondition.duplicate_title_check_scope !== 'None'"
                        v-model.number="searchCondition.duplicate_title_check_period_days" type="number" min="0"
                        label="録画履歴の確認期間（日）" variant="outlined" density="compact" hide-details />
                    <p>一致する番組を30秒ごとに確認して予約します。同じ番組の予約は重複して登録しません。</p>
                    <p>条件の変更・無効化・削除後も、登録済みの予約は残ります。予約一覧で変更・削除してください。</p>
                    <v-btn variant="outlined" :loading="isSearching" @click="preview">一致する番組を確認</v-btn>
                    <p v-if="previewCount !== null">現在の番組表で{{ previewCount }}件が一致します。</p>
                    <ul v-if="previewPrograms.length > 0" class="condition-editor__preview">
                        <li v-for="program in previewPrograms" :key="program.id">
                            {{ dayjs(program.start_time).format('M/D HH:mm') }}
                            <span v-html="ProgramUtils.decorateProgramInfo(program, 'title')"></span>
                        </li>
                    </ul>
                </div>
            </div>
        </v-card-text>
        <v-card-actions>
            <v-spacer />
            <v-btn :disabled="isSaving" @click="$emit('close')">キャンセル</v-btn>
            <v-btn color="primary" variant="flat" :loading="isSaving" :disabled="tuners === null" @click="save">保存</v-btn>
        </v-card-actions>
    </v-card>
</template>
<script lang="ts" setup>
import { computed, onMounted, ref, toRaw } from 'vue';

import ProgramSearchFilters from '@/components/Programs/ProgramSearchFilters.vue';
import Message from '@/message';
import { ILiveChannel } from '@/services/Channels';
import Programs, { IProgram, IProgramSearchConditionDefault } from '@/services/Programs';
import ReservationConditions, { IReservationCondition } from '@/services/ReservationConditions';
import Reservations, { IRecordingTuner, IRecordSettingsDefault } from '@/services/Reservations';
import { dayjs, ProgramUtils } from '@/utils';

const props = defineProps<{
    condition: IReservationCondition | null;
    channels: ILiveChannel[];
}>();
const emit = defineEmits<{
    (e: 'close'): void;
    (e: 'saved'): void;
}>();
const searchCondition = ref(structuredClone(toRaw(props.condition?.program_search_condition ?? IProgramSearchConditionDefault)));
const recordSettings = ref(structuredClone(toRaw(props.condition?.record_settings ?? {
    ...IRecordSettingsDefault, is_event_relay_follow_enabled: false,
})));
const tuners = ref<IRecordingTuner[] | null>(null);
const isSaving = ref(false);
const isSearching = ref(false);
const previewCount = ref<number | null>(null);
const previewPrograms = ref<IProgram[]>([]);
const priorityOptions = [1, 2, 3, 4, 5];
const duplicateOptions = [
    { title: '録画済みでも予約する', value: 'None' },
    { title: '同じチャンネルで録画済みなら無効にする', value: 'SameChannelOnly' },
    { title: 'どのチャンネルでも録画済みなら無効にする', value: 'AllChannels' },
];
const tunerOptions = computed(() => {
    const options: { title: string; value: string | null }[] = [{ title: '自動', value: null }];
    options.push(...(tuners.value ?? []).map(tuner => ({ title: tuner.name, value: tuner.name })));
    const selected = recordSettings.value.preferred_tuner_name;
    if (selected !== null && !options.some(option => option.value === selected)) {
        options.push({ title: `${selected}（現在利用できません）`, value: selected });
    }
    return options;
});

const preview = async () => {
    isSearching.value = true;
    try {
        const result = await Programs.searchPrograms({ ...searchCondition.value, is_enabled: true });
        if (result !== null) {
            previewCount.value = result.total;
            previewPrograms.value = result.programs.slice(0, 10);
        }
    } finally {
        isSearching.value = false;
    }
};

const save = async () => {
    isSaving.value = true;
    try {
        const saved = props.condition === null
            ? await ReservationConditions.addReservationCondition(searchCondition.value, recordSettings.value)
            : await ReservationConditions.updateReservationCondition(props.condition.id, searchCondition.value, recordSettings.value);
        if (saved) {
            Message.success('キーワード自動予約条件を保存しました。');
            emit('saved');
        }
    } finally {
        isSaving.value = false;
    }
};

onMounted(async () => {
    tuners.value = await Reservations.fetchRecordingTuners();
});
</script>
<style lang="scss" scoped>
.condition-editor {
    &__columns {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
        gap: 24px;

        @include smartphone-vertical {
            grid-template-columns: minmax(0, 1fr);
        }
    }

    &__settings {
        display: flex;
        flex-direction: column;
        gap: 20px;
    }

    &__preview {
        padding-left: 20px;
        li { margin-bottom: 12px; }
    }
}
</style>
