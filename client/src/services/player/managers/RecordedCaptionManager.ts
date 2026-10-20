import { CanvasRenderer } from 'aribb24.js';
import DPlayer from 'dplayer';

import APIClient from '@/services/APIClient';
import PlayerManager from '@/services/player/PlayerManager';
import Utils from '@/utils';

interface IRecordedCaptions {
    version: 1;
    packets: {
        pts: number;
        data: string;
    }[];
}

interface ICaptionPacket {
    pts: number;
    data: Uint8Array;
}

class RecordedCaptionManager implements PlayerManager {

    public readonly restart_required_when_quality_switched = false;
    private readonly player: DPlayer;
    private readonly video_id: number;
    private destroyed = false;
    private renderer: CanvasRenderer | null = null;
    private superimpose_renderer: CanvasRenderer | null = null;
    private packets: ICaptionPacket[] = [];
    private readonly replayCurrentCaptions = () => {
        for (const [identifier, renderer] of [[0x80, this.renderer], [0x81, this.superimpose_renderer]] as const) {
            let current: ICaptionPacket | null = null;
            for (const packet of this.packets) {
                if (packet.data[0] === identifier && packet.pts <= this.player.video.currentTime &&
                    (current === null || packet.pts >= current.pts)) {
                    current = packet;
                }
            }
            if (current !== null) renderer?.pushRawData(current.pts, current.data);
        }
    };

    constructor(player: DPlayer, video_id: number) {
        this.player = player;
        this.video_id = video_id;
    }

    public async init(): Promise<void> {
        this.destroyed = false;
        const response = await APIClient.get<IRecordedCaptions>(`/videos/${this.video_id}/captions`);
        if (this.destroyed || response.type === 'error') {
            return;
        }
        if (response.data.version !== 1) {
            this.player.notice('保存された字幕の形式に対応していません。', 5000);
            return;
        }

        const renderer = new CanvasRenderer({
            ...this.player.options.pluginOptions.aribb24,
            data_identifier: 0x80,
            enableAutoInBandMetadataTextTrackDetection: false,
        });
        this.renderer = renderer;
        this.player.plugins.aribb24Caption = renderer;
        renderer.attachMedia(this.player.video);
        if (this.player.template.subtitle.classList.contains('dplayer-subtitle-hide')) {
            renderer.hide();
        }
        if (this.player.options.pluginOptions.aribb24?.disableSuperimposeRenderer !== true) {
            this.superimpose_renderer = new CanvasRenderer({
                ...this.player.options.pluginOptions.aribb24,
                data_identifier: 0x81,
                enableAutoInBandMetadataTextTrackDetection: false,
            });
            this.player.plugins.aribb24Superimpose = this.superimpose_renderer;
            this.superimpose_renderer.attachMedia(this.player.video);
        }
        // aribb24.jsはシーク中に描画を消すため、完了後と字幕再表示時に現在の字幕を再投入する。
        this.player.video.addEventListener('seeked', this.replayCurrentCaptions);
        this.player.on('subtitle_show', this.replayCurrentCaptions);

        try {
            for (const [index, packet] of response.data.packets.entries()) {
                const binary = atob(packet.data);
                const data = Uint8Array.from(binary, character => character.charCodeAt(0));
                const target = data[0] === 0x81 ? this.superimpose_renderer : renderer;
                if (target?.pushRawData(packet.pts, data)) {
                    this.packets.push({pts: packet.pts, data});
                }
                if (index % 100 === 99) {
                    await Utils.sleep(0);
                    if (this.destroyed) return;
                }
            }
            this.replayCurrentCaptions();
        } catch (error) {
            console.error('[RecordedCaptionManager] Failed to load captions.', error);
            await this.destroy();
            this.player.notice('保存された字幕を読み込めませんでした。', 5000);
        }
    }

    public async destroy(): Promise<void> {
        this.destroyed = true;
        this.player.video.removeEventListener('seeked', this.replayCurrentCaptions);
        this.player.off('subtitle_show', this.replayCurrentCaptions);
        this.renderer?.dispose();
        this.superimpose_renderer?.dispose();
        if (this.player.plugins.aribb24Caption === this.renderer) {
            delete this.player.plugins.aribb24Caption;
        }
        if (this.player.plugins.aribb24Superimpose === this.superimpose_renderer) {
            delete this.player.plugins.aribb24Superimpose;
        }
        this.renderer = null;
        this.superimpose_renderer = null;
        this.packets = [];
    }
}

export default RecordedCaptionManager;
