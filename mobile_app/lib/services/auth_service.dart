import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../database/app_database.dart';
import 'api_client.dart';

class AuthService {
  final ApiClient _api;
  final AppDatabase _db;
  final FlutterSecureStorage _storage;

  AuthService(this._api, this._db, {FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  Future<bool> login(String username, String password) async {
    try {
      final data = await _api.login(username, password);

      // Store user info locally
      if (data['user'] != null) {
        final user = data['user'];
        await _db.into(_db.appUsers).insertOnConflictUpdate(
              AppUsersCompanion.insert(
                id: Value(user['id']),
                username: user['username'],
                email: Value(user['email'] ?? ''),
                firstName: Value(user['first_name'] ?? ''),
                lastName: Value(user['last_name'] ?? ''),
              ),
            );
        await _storage.write(key: 'current_user_id', value: '${user['id']}');
      }

      return true;
    } catch (e) {
      return false;
    }
  }

  Future<void> logout() async {
    await _api.logout();
    await _storage.delete(key: 'current_user_id');
  }

  Future<bool> isLoggedIn() async {
    return await _api.hasValidToken();
  }

  Future<int?> getCurrentUserId() async {
    final id = await _storage.read(key: 'current_user_id');
    return id != null ? int.tryParse(id) : null;
  }
}

final authServiceProvider = Provider<AuthService>((ref) {
  return AuthService(
    ref.watch(apiClientProvider),
    ref.watch(databaseProvider),
  );
});

final authStateProvider = FutureProvider<bool>((ref) async {
  return ref.watch(authServiceProvider).isLoggedIn();
});
