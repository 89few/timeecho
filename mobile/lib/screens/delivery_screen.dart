import 'package:flutter/material.dart';

import 'my_letters_screen.dart';
import 'write_letter_screen.dart';

class DeliveryScreen extends StatelessWidget {
  const DeliveryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const DefaultTabController(
      length: 2,
      child: Column(
        children: [
          TabBar(
            tabs: [
              Tab(text: '写纸飞机'),
              Tab(text: '我的投递'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: [WriteLetterScreen(), MyLettersScreen()],
            ),
          ),
        ],
      ),
    );
  }
}
