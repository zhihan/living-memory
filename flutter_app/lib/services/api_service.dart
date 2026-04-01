import 'dart:convert';

import 'package:http/http.dart' as http;

import '../app/config.dart';
import '../models/check_in.dart';
import '../models/occurrence.dart';
import '../models/series.dart';
import '../models/room.dart';
import '../shared/errors/api_exception.dart';
import 'auth_service.dart';

class ApiService {
  final AuthService _auth;
  final http.Client _client = http.Client();

  ApiService(this._auth);

  String get _baseUrl => AppConfig.apiBaseUrl;

  Future<Map<String, String>> _headers() async {
    final token = await _auth.getIdToken();
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  Future<http.Response> _sendRequest(
    String method,
    Uri uri,
    Map<String, String> headers,
    Map<String, dynamic>? body,
  ) async {
    switch (method) {
      case 'GET':
        return _client.get(uri, headers: headers);
      case 'POST':
        return _client.post(uri,
            headers: headers, body: body != null ? jsonEncode(body) : null);
      case 'PATCH':
        return _client.patch(uri,
            headers: headers, body: body != null ? jsonEncode(body) : null);
      case 'DELETE':
        return _client.delete(uri, headers: headers);
      default:
        throw ArgumentError('Unsupported method: $method');
    }
  }

  Future<dynamic> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
  }) async {
    final uri = Uri.parse('$_baseUrl$path').replace(queryParameters: queryParams);
    final headers = await _headers();

    http.Response response = await _sendRequest(method, uri, headers, body);

    // Retry once on 401 with fresh token
    if (response.statusCode == 401) {
      final freshToken = await _auth.getIdToken(forceRefresh: true);
      if (freshToken != null) {
        final retryHeaders = {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $freshToken',
        };
        response = await _sendRequest(method, uri, retryHeaders, body);
      }
    }

    if (response.statusCode == 204) return null;

    if (response.statusCode >= 400) {
      String message;
      try {
        final decoded = jsonDecode(response.body);
        message = decoded['detail'] ?? response.body;
      } catch (_) {
        message = response.body;
      }
      throw ApiException(statusCode: response.statusCode, message: message);
    }

    return response.body.isNotEmpty ? jsonDecode(response.body) : null;
  }

  // --- Rooms ---

  Future<List<Room>> listRooms() async {
    final data = await _request('GET', '/v2/rooms');
    final list = data['rooms'] as List;
    return list
        .map((r) => Room.fromJson(r as Map<String, dynamic>))
        .toList();
  }

  Future<Room> getRoom(String id) async {
    final data = await _request('GET', '/v2/rooms/$id');
    return Room.fromJson(data as Map<String, dynamic>);
  }

  Future<Room> createRoom({
    required String title,
    String type = 'shared',
    String timezone = 'UTC',
    String? description,
  }) async {
    final data = await _request('POST', '/v2/rooms', body: {
      'title': title,
      'type': type,
      'timezone': timezone,
      if (description != null) 'description': description,
    });
    return Room.fromJson(data as Map<String, dynamic>);
  }

  Future<Room> updateRoom(
      String id, Map<String, dynamic> updates) async {
    final data = await _request('PATCH', '/v2/rooms/$id', body: updates);
    return Room.fromJson(data as Map<String, dynamic>);
  }

  Future<void> deleteRoom(String id) async {
    await _request('DELETE', '/v2/rooms/$id');
  }

  // --- Members ---

  Future<List<MemberDetail>> listMembers(String roomId) async {
    final data =
        await _request('GET', '/v2/rooms/$roomId/members');
    final list = data['member_details'] as List;
    return list
        .map((m) => MemberDetail.fromJson(m as Map<String, dynamic>))
        .toList();
  }

  Future<void> addMember(String roomId, String uid, String role) async {
    await _request('POST', '/v2/rooms/$roomId/members',
        body: {'uid': uid, 'role': role});
  }

  Future<void> removeMember(String roomId, String uid) async {
    await _request('DELETE', '/v2/rooms/$roomId/members/$uid');
  }

  // --- Invites ---

  Future<Map<String, dynamic>> createInvite(
      String roomId, String role) async {
    final data = await _request(
        'POST', '/v2/rooms/$roomId/invites',
        body: {'role': role});
    return data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> acceptInvite(String inviteId) async {
    final data = await _request('POST', '/v2/invites/$inviteId/accept');
    return data as Map<String, dynamic>;
  }

  // --- Series ---

  Future<List<Series>> listSeries(String roomId) async {
    final data =
        await _request('GET', '/v2/rooms/$roomId/series');
    final list = data['series'] as List;
    return list
        .map((s) => Series.fromJson(s as Map<String, dynamic>))
        .toList();
  }

  Future<Series> getSeries(String id) async {
    final data = await _request('GET', '/v2/series/$id');
    return Series.fromJson(data as Map<String, dynamic>);
  }

  Future<Series> createSeries(
      String roomId, Map<String, dynamic> body) async {
    final data = await _request(
        'POST', '/v2/rooms/$roomId/series',
        body: body);
    return Series.fromJson(data as Map<String, dynamic>);
  }

  Future<Series> updateSeries(
      String id, Map<String, dynamic> updates) async {
    final data = await _request('PATCH', '/v2/series/$id', body: updates);
    return Series.fromJson(data as Map<String, dynamic>);
  }

  Future<void> deleteSeries(String id) async {
    await _request('DELETE', '/v2/series/$id');
  }

  Future<Map<String, dynamic>> getCheckInReport(String seriesId) async {
    final data =
        await _request('GET', '/v2/series/$seriesId/check-in-report');
    return data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> repopulateRotation(
      String seriesId, String occurrenceId) async {
    final data = await _request('POST',
        '/v2/series/$seriesId/occurrences/$occurrenceId/regenerate-rotation');
    return data as Map<String, dynamic>;
  }

  // --- Occurrences ---

  Future<List<Occurrence>> listRoomOccurrences(
      String roomId, {String? status}) async {
    final data = await _request(
        'GET', '/v2/rooms/$roomId/occurrences',
        queryParams: status != null ? {'status': status} : null);
    final list = data['occurrences'] as List;
    return list
        .map((o) => Occurrence.fromJson(o as Map<String, dynamic>))
        .toList();
  }

  Future<List<Occurrence>> listSeriesOccurrences(
      String seriesId, {String? status}) async {
    final data = await _request(
        'GET', '/v2/series/$seriesId/occurrences',
        queryParams: status != null ? {'status': status} : null);
    final list = data['occurrences'] as List;
    return list
        .map((o) => Occurrence.fromJson(o as Map<String, dynamic>))
        .toList();
  }

  Future<Map<String, dynamic>> generateOccurrences(
      String seriesId, String startDate, String endDate,
      {String? timezone}) async {
    final data = await _request(
        'POST', '/v2/series/$seriesId/occurrences/generate',
        body: {
          'start_date': startDate,
          'end_date': endDate,
          if (timezone != null) 'room_timezone': timezone,
        });
    return data as Map<String, dynamic>;
  }

  Future<Occurrence> createOccurrence(
      String seriesId, String scheduledFor,
      {String? location, String? host, bool? enableCheckIn}) async {
    final data = await _request(
        'POST', '/v2/series/$seriesId/occurrences',
        body: {
          'scheduled_for': scheduledFor,
          if (location != null) 'location': location,
          if (host != null) 'host': host,
          if (enableCheckIn != null) 'enable_check_in': enableCheckIn,
        });
    return Occurrence.fromJson(data as Map<String, dynamic>);
  }

  Future<Occurrence> getOccurrence(String id) async {
    final data = await _request('GET', '/v2/occurrences/$id');
    return Occurrence.fromJson(data as Map<String, dynamic>);
  }

  Future<Occurrence> updateOccurrence(
      String id, Map<String, dynamic> updates) async {
    final data =
        await _request('PATCH', '/v2/occurrences/$id', body: updates);
    return Occurrence.fromJson(data as Map<String, dynamic>);
  }

  Future<void> deleteOccurrence(String id) async {
    await _request('DELETE', '/v2/occurrences/$id');
  }

  // --- Check-ins ---

  Future<CheckIn> upsertCheckIn(
      String occurrenceId, String status, {String? note}) async {
    final data = await _request(
        'POST', '/v2/occurrences/$occurrenceId/check-ins',
        body: {'status': status, if (note != null) 'note': note});
    return CheckIn.fromJson(data as Map<String, dynamic>);
  }

  Future<List<CheckIn>> listCheckIns(String occurrenceId) async {
    final data = await _request(
        'GET', '/v2/occurrences/$occurrenceId/check-ins');
    final list = data['check_ins'] as List;
    return list
        .map((c) => CheckIn.fromJson(c as Map<String, dynamic>))
        .toList();
  }

  Future<CheckIn?> getMyCheckIn(String occurrenceId) async {
    final data = await _request(
        'GET', '/v2/occurrences/$occurrenceId/my-check-in');
    final ci = data['check_in'];
    return ci != null
        ? CheckIn.fromJson(ci as Map<String, dynamic>)
        : null;
  }

  Future<CheckIn> updateCheckIn(
      String checkInId, String status, {String? note}) async {
    final data = await _request('PATCH', '/v2/check-ins/$checkInId',
        body: {'status': status, if (note != null) 'note': note});
    return CheckIn.fromJson(data as Map<String, dynamic>);
  }

  Future<void> deleteCheckIn(String checkInId) async {
    await _request('DELETE', '/v2/check-ins/$checkInId');
  }

  // --- Telegram Bot ---

  Future<Map<String, dynamic>> connectTelegramBot(
      String roomId, String botToken, {String mode = 'read_only'}) async {
    final data = await _request('POST', '/v2/rooms/$roomId/telegram-bot',
        body: {'bot_token': botToken, 'mode': mode});
    return data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>?> getTelegramBot(String roomId) async {
    try {
      final data = await _request('GET', '/v2/rooms/$roomId/telegram-bot');
      return data as Map<String, dynamic>;
    } on ApiException catch (e) {
      if (e.statusCode == 404) return null;
      rethrow;
    }
  }

  Future<Map<String, dynamic>> updateTelegramBotMode(
      String roomId, String mode) async {
    final data = await _request('PATCH', '/v2/rooms/$roomId/telegram-bot',
        body: {'mode': mode});
    return data as Map<String, dynamic>;
  }

  Future<void> deleteTelegramBot(String roomId) async {
    await _request('DELETE', '/v2/rooms/$roomId/telegram-bot');
  }

  Future<Map<String, dynamic>> generateTelegramLinkCode(String roomId) async {
    final data =
        await _request('POST', '/v2/rooms/$roomId/telegram-bot/link-code');
    return data as Map<String, dynamic>;
  }
}
