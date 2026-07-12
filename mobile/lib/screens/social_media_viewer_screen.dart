import 'package:audioplayers/audioplayers.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../core/app_config.dart';
import '../models/social.dart';

class SocialMediaViewerScreen extends StatefulWidget {
  const SocialMediaViewerScreen({super.key, required this.media});

  final SocialMedia media;

  @override
  State<SocialMediaViewerScreen> createState() =>
      _SocialMediaViewerScreenState();
}

class _SocialMediaViewerScreenState extends State<SocialMediaViewerScreen> {
  VideoPlayerController? _videoController;
  final _audioPlayer = AudioPlayer();
  bool _audioPlaying = false;
  Duration _audioPosition = Duration.zero;
  Duration _audioDuration = Duration.zero;
  String? _error;

  String get _url {
    final value = widget.media.url;
    if (value.startsWith('http://') || value.startsWith('https://')) {
      return value;
    }
    return '${AppConfig.apiBaseUrl}${value.startsWith('/') ? '' : '/'}$value';
  }

  bool get _isVideo => widget.media.kind.toLowerCase() == 'video';
  bool get _isAudio =>
      const ['audio', 'voice'].contains(widget.media.kind.toLowerCase());

  @override
  void initState() {
    super.initState();
    if (_isVideo) _initVideo();
    if (_isAudio) {
      _audioPlayer.onPlayerStateChanged.listen((state) {
        if (mounted) {
          setState(() => _audioPlaying = state == PlayerState.playing);
        }
      });
      _audioPlayer.onPositionChanged.listen((position) {
        if (mounted) setState(() => _audioPosition = position);
      });
      _audioPlayer.onDurationChanged.listen((duration) {
        if (mounted) setState(() => _audioDuration = duration);
      });
    }
  }

  Future<void> _initVideo() async {
    final controller = VideoPlayerController.networkUrl(Uri.parse(_url));
    _videoController = controller;
    try {
      await controller.initialize();
      await controller.play();
      if (mounted) setState(() {});
    } catch (error) {
      if (mounted) setState(() => _error = '视频加载失败：$error');
    }
  }

  Future<void> _toggleAudio() async {
    try {
      if (_audioPlaying) {
        await _audioPlayer.pause();
      } else if (_audioPosition > Duration.zero) {
        await _audioPlayer.resume();
      } else {
        await _audioPlayer.play(UrlSource(_url));
      }
    } catch (error) {
      if (mounted) setState(() => _error = '语音加载失败：$error');
    }
  }

  @override
  void dispose() {
    _videoController?.dispose();
    _audioPlayer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF111218),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        title: Text(
          _isVideo
              ? '视频'
              : _isAudio
                  ? '语音'
                  : '图片',
        ),
      ),
      body: SafeArea(
        child: Center(
          child: _isVideo
              ? _buildVideo()
              : _isAudio
                  ? _buildAudio()
                  : _buildImage(),
        ),
      ),
    );
  }

  Widget _buildImage() {
    return InteractiveViewer(
      minScale: .7,
      maxScale: 5,
      child: CachedNetworkImage(
        imageUrl: _url,
        fit: BoxFit.contain,
        placeholder: (_, __) =>
            const CircularProgressIndicator(color: Colors.white),
        errorWidget: (_, __, ___) => const _ViewerError(message: '图片加载失败'),
      ),
    );
  }

  Widget _buildVideo() {
    final controller = _videoController;
    if (_error != null) return _ViewerError(message: _error!);
    if (controller == null || !controller.value.isInitialized) {
      return const CircularProgressIndicator(color: Colors.white);
    }
    return GestureDetector(
      onTap: () async {
        controller.value.isPlaying
            ? await controller.pause()
            : await controller.play();
        if (mounted) setState(() {});
      },
      child: Stack(
        alignment: Alignment.center,
        children: [
          AspectRatio(
            aspectRatio: controller.value.aspectRatio,
            child: VideoPlayer(controller),
          ),
          if (!controller.value.isPlaying)
            Container(
              width: 66,
              height: 66,
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: .45),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.play_arrow_rounded,
                color: Colors.white,
                size: 42,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildAudio() {
    final max = _audioDuration.inMilliseconds <= 0
        ? 1.0
        : _audioDuration.inMilliseconds.toDouble();
    final current =
        _audioPosition.inMilliseconds.clamp(0, max.toInt()).toDouble();
    return Padding(
      padding: const EdgeInsets.all(28),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 520),
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: .08),
          borderRadius: BorderRadius.circular(28),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 84,
              height: 84,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: .12),
                shape: BoxShape.circle,
              ),
              child: IconButton(
                onPressed: _toggleAudio,
                iconSize: 48,
                color: Colors.white,
                icon: Icon(
                  _audioPlaying
                      ? Icons.pause_rounded
                      : Icons.play_arrow_rounded,
                ),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              '听见这一刻',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w800,
                fontSize: 20,
              ),
            ),
            Slider(
              value: current,
              max: max,
              onChanged: (value) =>
                  _audioPlayer.seek(Duration(milliseconds: value.round())),
            ),
            Text(
              '${_format(_audioPosition)} / ${_format(_audioDuration)}',
              style: const TextStyle(color: Colors.white70),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  _error!,
                  style: const TextStyle(color: Colors.redAccent),
                ),
              ),
          ],
        ),
      ),
    );
  }

  String _format(Duration value) =>
      '${value.inMinutes.toString().padLeft(2, '0')}:${(value.inSeconds % 60).toString().padLeft(2, '0')}';
}

class _ViewerError extends StatelessWidget {
  const _ViewerError({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.broken_image_outlined,
              color: Colors.white70, size: 56),
          const SizedBox(height: 12),
          Text(message, style: const TextStyle(color: Colors.white70)),
        ],
      );
}
