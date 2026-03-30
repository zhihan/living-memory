import 'dart:convert';

import 'package:http/http.dart' as http;

import '../app/config.dart';
import '../models/check_in.dart';
import '../models/occurrence.dart';
import '../models/series.dart';
import '../models/workspace.dart';
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

  Future<dynamic> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
  }) async {
    final uri = Uri.parse('$_baseUrl$path').replace(queryParameters: queryParams);
    final headers = await _headers();

    http.Response response;
    switch (method) {
      case 'GET':
        response = await _client.get(uri, headers: headers);
      case 'POST':
        response = await _client.post(uri,
            headers: headers, body: body != null ? jsonEncode(body) : null);
      case 'PATCH':
        response = await _client.patch(uri,
            headers: headers, body: body != null ? jsonEncode(body) : null);
      case 'DELETE':
        response = await _client.delete(uri, headers: headers);
      default:
        throw ArgumentError('Unsupported method: $method');
    }

    // Retry once on 401 with fresh token
    if (response.statusCode == 401) {
      final freshToken = await _auth.getIdToken(forceRefresh: true);
      if (freshToken != null) {
        final retryHeaders = {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $freshToken',
        };
        switch (method) {
          case 'GET':
            response = await _client.get(uri, headers: retryHeaders);
          case 'POST':
            response = await _client.post(uri,
                headers: retryHeaders,
                body: body != null ? jsonEncode(body) : null);
          case 'PATCH':
            response = await _client.patch(uri,
                headers: retryHeaders,
                body: body != null ? jsonEncode(body) : null);
          case 'DELETE':
            response = await _client.delete(uri, headers: retryHeaders);
        }
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

  // --- Workspaces ---

  Future<List<Workspace>> listWorkspaces() async {
    final data = await _request('GET', '/v2/workspaces');
    final list = data['workspaces'] as List;
    return list
        .map((w) => Workspace.fromJson(w as Map<String, dynamic>))
        .toList();
  }

  Future<Workspace> getWorkspace(String id) async {
    final data = await _request('GET', '/v2/workspaces/$id');
    return Workspace.fromJson(data as Map<String, dynamic>);
  }

  Future<Workspace> createWorkspace({
    required String title,
    String type = 'shared',
    String timezone = 'UTC',
    String? description,
  }) async {
    final data = await _request('POST', '/v2/workspaces', body: {
      'title': title,
      'type': type,
      'timezone': timezone,
      if (description != null) 'description': description,
    });
    return Workspace.fromJson(data as Map<String, dynamic>);
  }

  Future<Workspace> updateWorkspace(
      String id, Map<String, dynamic> updates) async {
    final data = await _request('PATCH', '/v2/workspaces/$id', body: updates);
    return Workspace.fromJson(data as Map<String, dynamic>);
  }

  Future<void> deleteWorkspace(String id) async {
    await _request('DELETE', '/v2/workspaces/$id');
  }

  // --- Members ---

  Future<List<MemberDetail>> listMembers(String workspaceId) async {
    final data =
        await _request('GET', '/v2/workspaces/$workspaceId/members');
    final list = data['member_details'] as List;
    return list
        .map((m) => MemberDetail.fromJson(m as Map<String, dynamic>))
        .toList();
  }

  Future<void> addMember(String workspaceId, String uid, String role) async {
    await _request('POST', '/v2/workspaces/$workspaceId/members',
        body: {'uid': uid, 'role': role});
  }

  Future<void> removeMember(String workspaceId, String uid) async {
    await _request('DELETE', '/v2/workspaces/$workspaceId/members/$uid');
  }

  // --- Invites ---

  Future<Map<String, dynamic>> createInvite(
      String workspaceId, String role) async {
    final data = await _request(
        'POST', '/v2/workspaces/$workspaceId/invites',
        body: {'role': role});
    return data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> acceptInvite(String inviteId) async {
    final data = await _request('POST', '/v2/invites/$inviteId/accept');
    return data as Map<String, dynamic>;
  }

  // --- Series ---

  Future<List<Series>> listSeries(String workspaceId) async {
    final data =
        await _request('GET', '/v2/workspaces/$workspaceId/series');
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
      String workspaceId, Map<String, dynamic> body) async {
    final data = await _request(
        'POST', '/v2/workspaces/$workspaceId/series',
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

  // --- Occurrences ---

  Future<List<Occurrence>> listWorkspaceOccurrences(
      String workspaceId, {String? status}) async {
    final data = await _request(
        'GET', '/v2/workspaces/$workspaceId/occurrences',
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
          if (timezone != null) 'workspace_timezone': timezone,
        });
    return data as Map<String, dynamic>;
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
}
