import '../core/api_client.dart';
import '../models/chat_room.dart';
import '../models/letter.dart';

class SalvageService {
  SalvageService({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();
  final ApiClient _api;

  Future<SalvagedLetter?> salvage({String? emotion}) async {
    final data = await _api.post('/api/salvage', data: {'emotion': emotion});
    if (data['letter_id'] == null) return null;
    return SalvagedLetter.fromJson(data);
  }

  Future<ChatRoomInfo> reply(int letterId) async {
    final data = await _api.post('/api/salvage/$letterId/reply');
    final roomId = int.tryParse('${data['room_id']}') ?? 0;
    return ChatRoomInfo(roomId: roomId, letterId: letterId, status: 'ACTIVE');
  }
}
