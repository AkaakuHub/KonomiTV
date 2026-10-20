import DPlayer from 'dplayer';
import mpegts from 'mpegts.js';

import APIClient from '@/services/APIClient';
import useChannelsStore from '@/stores/ChannelsStore';
import usePlayerStore from '@/stores/PlayerStore';

type Phase = 'initial' | '5s' | '15s' | '30s' | 'native-error' | 'mpegts-error';

class LivePlaybackDiagnostics {
    private readonly video: HTMLVideoElement;
    private readonly session_id = crypto.randomUUID();
    private readonly started_at = performance.now();
    private readonly timers: number[] = [];
    private readonly mpegts_player: mpegts.Player | undefined;
    private mpegts_error: string | null = null;
    private destroyed = false;

    constructor(
        private readonly player: DPlayer,
        private readonly channel_id: string,
        private readonly quality: string,
    ) {
        this.video = player.video;
        this.mpegts_player = player.plugins.mpegts;
        for (const [seconds, phase] of [[5, '5s'], [15, '15s'], [30, '30s']] as const) {
            this.timers.push(window.setTimeout(() => this.send(phase), seconds * 1000));
        }
        this.video.addEventListener('error', this.onNativeError, {once: true});
        this.mpegts_player?.on(mpegts.Events.ERROR, this.onMpegtsError);
        this.send('initial');
    }

    private readonly onNativeError = (): void => this.send('native-error');

    private readonly onMpegtsError = (type: string, detail: string): void => {
        if (this.mpegts_error !== null) return;
        this.mpegts_error = `${type}: ${detail}`.slice(0, 512);
        this.send('mpegts-error');
    };

    private send(phase: Phase): void {
        if (this.destroyed || this.player.video !== this.video ||
            this.player.plugins.mpegts !== this.mpegts_player) return;
        const player_store = usePlayerStore();
        const channels_store = useChannelsStore();
        const quality = typeof this.video.getVideoPlaybackQuality === 'function' ?
            this.video.getVideoPlaybackQuality() : null;
        const media_info = this.mpegts_player?.mediaInfo;
        const buffered: [number, number][] = [];
        for (let index = 0; index < Math.min(this.video.buffered.length, 16); index++) {
            buffered.push([this.video.buffered.start(index), this.video.buffered.end(index)]);
        }
        void APIClient.post<void>(`/streams/live/${this.channel_id}/${this.quality}/diagnostics`, {
            revision: 'live-playback-20261021',
            session_id: this.session_id,
            phase,
            user_agent: navigator.userAgent.slice(0, 512),
            player_type: this.player.type,
            elapsed_seconds: (performance.now() - this.started_at) / 1000,
            ready_state: this.video.readyState,
            network_state: this.video.networkState,
            current_time: Number.isFinite(this.video.currentTime) ? this.video.currentTime : null,
            playback_rate: this.video.playbackRate,
            paused: this.video.paused,
            muted: this.video.muted,
            volume: this.video.volume,
            width: this.video.videoWidth,
            height: this.video.videoHeight,
            decoded_frames: quality?.totalVideoFrames ?? null,
            dropped_frames: quality?.droppedVideoFrames ?? null,
            buffered,
            video_codec: media_info && 'videoCodec' in media_info ? media_info.videoCodec ?? null : null,
            audio_codec: media_info && 'audioCodec' in media_info ? media_info.audioCodec ?? null : null,
            media_error_code: this.video.error?.code ?? null,
            media_error: this.video.error?.message.slice(0, 512) ?? null,
            mpegts_error: this.mpegts_error,
            media_source: typeof window.MediaSource === 'function',
            managed_media_source: 'ManagedMediaSource' in window && typeof window.ManagedMediaSource === 'function',
            loading: player_store.is_loading,
            buffering: player_store.is_video_buffering,
            program_id: channels_store.channel.current.program_present?.id ?? null,
        });
    }

    public destroy(): void {
        this.destroyed = true;
        for (const timer of this.timers) window.clearTimeout(timer);
        this.video.removeEventListener('error', this.onNativeError);
        if (this.player.plugins.mpegts === this.mpegts_player) {
            this.mpegts_player?.off(mpegts.Events.ERROR, this.onMpegtsError);
        }
    }
}

export default LivePlaybackDiagnostics;
