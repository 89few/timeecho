import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../core/theme.dart';
import '../models/social.dart';
import '../services/social_service.dart';

class CreatePostScreen extends StatefulWidget {
  const CreatePostScreen({super.key});

  @override
  State<CreatePostScreen> createState() => _CreatePostScreenState();
}

class _CreatePostScreenState extends State<CreatePostScreen> {
  final _text = TextEditingController();
  final _picker = ImagePicker();
  final _recorder = AudioRecorder();
  final _service = SocialService();
  final List<_PendingMedia> _pending = [];
  bool _publishing = false;
  bool _recording = false;
  String _visibility = 'PUBLIC';
  String? _message;

  @override
  void dispose() {
    _text.dispose();
    _recorder.dispose();
    super.dispose();
  }

  Future<void> _pickImages() async {
    final files = await _picker.pickMultiImage(
      imageQuality: 82,
      maxWidth: 1920,
    );
    if (!mounted || files.isEmpty) return;
    final room = 9 - _pending.length;
    setState(
      () => _pending.addAll(
        files.take(room).map((file) => _PendingMedia('image', file.path)),
      ),
    );
  }

  Future<void> _pickVideo() async {
    if (_pending.length >= 9) return;
    final file = await _picker.pickVideo(
      source: ImageSource.gallery,
      maxDuration: const Duration(minutes: 3),
    );
    if (file != null && mounted) {
      setState(() => _pending.add(_PendingMedia('video', file.path)));
    }
  }

  Future<void> _toggleRecording() async {
    if (_recording) {
      final path = await _recorder.stop();
      if (!mounted) return;
      setState(() {
        _recording = false;
        if (path != null) _pending.add(_PendingMedia('audio', path));
      });
      return;
    }
    if (_pending.length >= 9) return;
    if (!await _recorder.hasPermission()) {
      setState(() => _message = '需要麦克风权限才能录制语音');
      return;
    }
    final directory = await getTemporaryDirectory();
    final path =
        '${directory.path}/post_voice_${DateTime.now().millisecondsSinceEpoch}.m4a';
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.aacLc),
      path: path,
    );
    if (mounted) {
      setState(() {
        _recording = true;
        _message = '正在录音，再点一次结束';
      });
    }
  }

  Future<void> _publish() async {
    if (_text.text.trim().isEmpty && _pending.isEmpty) {
      setState(() => _message = '写点什么，或者添加一段媒体');
      return;
    }
    if (_recording) await _toggleRecording();
    setState(() {
      _publishing = true;
      _message = _pending.isEmpty ? '正在发布…' : '正在上传 0/${_pending.length}…';
    });
    try {
      final uploaded = <SocialMedia>[];
      for (var index = 0; index < _pending.length; index++) {
        final media = await _service.uploadMedia(_pending[index].path);
        uploaded.add(media);
        if (mounted) {
          setState(() => _message = '正在上传 ${index + 1}/${_pending.length}…');
        }
      }
      final post = await _service.createPost(
        text: _text.text,
        media: uploaded,
        visibility: _visibility,
      );
      if (!mounted) return;
      Navigator.pop(context, post);
    } catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _publishing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('发布动态'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: FilledButton(
              onPressed: _publishing ? null : _publish,
              child: const Text('发布'),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 10, 20, 20),
                children: [
                  Row(
                    children: [
                      const Icon(
                        Icons.visibility_outlined,
                        size: 20,
                        color: TimeEchoColors.muted,
                      ),
                      const SizedBox(width: 8),
                      const Text('谁可以看'),
                      const Spacer(),
                      DropdownButtonHideUnderline(
                        child: DropdownButton<String>(
                          value: _visibility,
                          borderRadius: BorderRadius.circular(16),
                          items: const [
                            DropdownMenuItem(
                              value: 'PUBLIC',
                              child: Text('所有人'),
                            ),
                            DropdownMenuItem(
                              value: 'FRIENDS',
                              child: Text('仅好友'),
                            ),
                            DropdownMenuItem(
                              value: 'PRIVATE',
                              child: Text('仅自己'),
                            ),
                          ],
                          onChanged: _publishing
                              ? null
                              : (value) => setState(
                                    () => _visibility = value ?? 'PUBLIC',
                                  ),
                        ),
                      ),
                    ],
                  ),
                  const Divider(height: 20),
                  TextField(
                    controller: _text,
                    minLines: 5,
                    maxLines: 12,
                    maxLength: 2000,
                    autofocus: true,
                    decoration: const InputDecoration(
                      hintText: '分享此刻的声音、光影或一句话…',
                      alignLabelWithHint: true,
                      counterText: '',
                      border: InputBorder.none,
                      filled: false,
                    ),
                  ),
                  if (_pending.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    GridView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      gridDelegate:
                          const SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: 3,
                        crossAxisSpacing: 8,
                        mainAxisSpacing: 8,
                      ),
                      itemCount: _pending.length,
                      itemBuilder: (context, index) => _PendingMediaTile(
                        media: _pending[index],
                        onRemove: _publishing
                            ? null
                            : () => setState(() => _pending.removeAt(index)),
                      ),
                    ),
                  ],
                  if (_message != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 16),
                      child: Row(
                        children: [
                          if (_publishing) ...[
                            const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            ),
                            const SizedBox(width: 10),
                          ],
                          Expanded(
                            child: Text(
                              _message!,
                              style: const TextStyle(
                                color: TimeEchoColors.muted,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
              decoration: const BoxDecoration(
                color: TimeEchoColors.surface,
                border: Border(top: BorderSide(color: Color(0x12000000))),
              ),
              child: SafeArea(
                top: false,
                child: Row(
                  children: [
                    _ComposerAction(
                      icon: Icons.photo_library_outlined,
                      label: '图片',
                      onTap: _publishing ? null : _pickImages,
                    ),
                    _ComposerAction(
                      icon: Icons.video_library_outlined,
                      label: '视频',
                      onTap: _publishing ? null : _pickVideo,
                    ),
                    _ComposerAction(
                      icon: _recording
                          ? Icons.stop_circle_outlined
                          : Icons.mic_none_rounded,
                      label: _recording ? '停止' : '语音',
                      color: _recording
                          ? Theme.of(context).colorScheme.error
                          : null,
                      onTap: _publishing ? null : _toggleRecording,
                    ),
                    const Spacer(),
                    Text(
                      '${_pending.length}/9',
                      style: const TextStyle(color: TimeEchoColors.muted),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PendingMedia {
  const _PendingMedia(this.kind, this.path);
  final String kind;
  final String path;
}

class _PendingMediaTile extends StatelessWidget {
  const _PendingMediaTile({required this.media, this.onRemove});
  final _PendingMedia media;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(16),
          child: media.kind == 'image'
              ? Image.file(File(media.path), fit: BoxFit.cover)
              : Container(
                  color: media.kind == 'video'
                      ? TimeEchoColors.mistBlue
                      : const Color(0xFFEAE2F0),
                  child: Icon(
                    media.kind == 'video'
                        ? Icons.play_circle_fill_rounded
                        : Icons.graphic_eq_rounded,
                    size: 38,
                    color: TimeEchoColors.duskPurple,
                  ),
                ),
        ),
        Positioned(
          right: 4,
          top: 4,
          child: IconButton.filled(
            visualDensity: VisualDensity.compact,
            onPressed: onRemove,
            iconSize: 16,
            style: IconButton.styleFrom(
              backgroundColor: Colors.black54,
              foregroundColor: Colors.white,
            ),
            icon: const Icon(Icons.close_rounded),
          ),
        ),
      ],
    );
  }
}

class _ComposerAction extends StatelessWidget {
  const _ComposerAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.color,
  });
  final IconData icon;
  final String label;
  final VoidCallback? onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color ?? TimeEchoColors.duskPurple),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(
                fontSize: 11,
                color: color ?? TimeEchoColors.muted,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
