import 'package:test/test.dart';
import 'package:event_ledger/shared/errors/api_exception.dart';

void main() {
  group('ApiException', () {
    test('toString includes status code and message', () {
      const ex = ApiException(statusCode: 404, message: 'Not found');
      expect(ex.toString(), 'ApiException(404): Not found');
    });

    test('properties are accessible', () {
      const ex = ApiException(statusCode: 403, message: 'Forbidden');
      expect(ex.statusCode, 403);
      expect(ex.message, 'Forbidden');
    });
  });
}
