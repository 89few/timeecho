import '../core/api_client.dart';
import '../models/letter.dart';

class LetterService {
  LetterService({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();
  final ApiClient _api;

  Future<LetterSummary> create({
    required String content,
    required String emotion,
    int? sealDays,
    int? sealSeconds,
  }) async {
    final payload = {
      'content': content,
      'emotion': emotion,
      if (sealSeconds != null)
        'seal_seconds': sealSeconds
      else
        'seal_days': sealDays ?? 1,
    };
    return LetterSummary.fromJson(
      await _api.post('/api/letters', data: payload),
    );
  }

  Future<List<LetterSummary>> mine({String? status}) async {
    final data = await _api.get(
      '/api/letters/mine',
      queryParameters: {if (status != null) 'status': status},
    );
    final items = data['items'];
    if (items is List) {
      return items
          .whereType<Map<String, dynamic>>()
          .map(LetterSummary.fromJson)
          .toList();
    }
    return const [];
  }

  Future<LetterDetail> detail(int id) async =>
      LetterDetail.fromJson(await _api.get('/api/letters/$id'));
}
