import 'package:flutter/material.dart';

import '../core/theme.dart';
import 'my_letters_screen.dart';
import 'salvage_screen.dart';
import 'write_letter_screen.dart';

class PlaneHubScreen extends StatefulWidget {
  const PlaneHubScreen({super.key});

  @override
  State<PlaneHubScreen> createState() => _PlaneHubScreenState();
}

class _PlaneHubScreenState extends State<PlaneHubScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(22, 18, 22, 12),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '纸飞机',
                      style: Theme.of(context)
                          .textTheme
                          .headlineMedium
                          ?.copyWith(fontWeight: FontWeight.w900),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 18),
          child: Container(
            height: 48,
            padding: const EdgeInsets.all(4),
            decoration: BoxDecoration(
              color: const Color(0xFFEDE7F2),
              borderRadius: BorderRadius.circular(16),
            ),
            child: TabBar(
              controller: _controller,
              dividerColor: Colors.transparent,
              indicatorSize: TabBarIndicatorSize.tab,
              indicator: BoxDecoration(
                color: TimeEchoColors.surface,
                borderRadius: BorderRadius.circular(13),
                boxShadow: const [
                  BoxShadow(color: Color(0x12000000), blurRadius: 8),
                ],
              ),
              labelStyle: const TextStyle(fontWeight: FontWeight.w800),
              tabs: const [
                Tab(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.edit_note_rounded, size: 18),
                      SizedBox(width: 4),
                      Text('写信'),
                    ],
                  ),
                ),
                Tab(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.air_rounded, size: 18),
                      SizedBox(width: 4),
                      Text('打捞'),
                    ],
                  ),
                ),
                Tab(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.inventory_2_outlined, size: 18),
                      SizedBox(width: 4),
                      Text('投递'),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 6),
        Expanded(
          child: TabBarView(
            controller: _controller,
            children: const [
              _KeepAliveTab(child: WriteLetterScreen()),
              _KeepAliveTab(child: SalvageScreen()),
              _KeepAliveTab(child: MyLettersScreen()),
            ],
          ),
        ),
      ],
    );
  }
}

class _KeepAliveTab extends StatefulWidget {
  const _KeepAliveTab({required this.child});
  final Widget child;

  @override
  State<_KeepAliveTab> createState() => _KeepAliveTabState();
}

class _KeepAliveTabState extends State<_KeepAliveTab>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return widget.child;
  }
}
