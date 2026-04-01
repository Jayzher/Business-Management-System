import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:logger/logger.dart';

import '../config/api_config.dart';

final _log = Logger();

class ApiClient {
  late final Dio _dio;
  final FlutterSecureStorage _storage;

  ApiClient({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage() {
    _dio = Dio(BaseOptions(
      baseUrl: Platform.isAndroid ? ApiConfig.baseUrl : ApiConfig.baseUrlIOS,
      connectTimeout: ApiConfig.connectTimeout,
      receiveTimeout: ApiConfig.receiveTimeout,
      headers: {'Content-Type': 'application/json'},
    ));

    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await _storage.read(key: 'access_token');
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        return handler.next(options);
      },
      onError: (error, handler) async {
        if (error.response?.statusCode == 401) {
          // Try refresh token
          final refreshed = await _refreshToken();
          if (refreshed) {
            // Retry the request
            final token = await _storage.read(key: 'access_token');
            error.requestOptions.headers['Authorization'] = 'Bearer $token';
            final response = await _dio.fetch(error.requestOptions);
            return handler.resolve(response);
          }
        }
        return handler.next(error);
      },
    ));
  }

  Future<bool> _refreshToken() async {
    try {
      final refreshToken = await _storage.read(key: 'refresh_token');
      if (refreshToken == null) return false;

      final response = await Dio().post(
        '${Platform.isAndroid ? ApiConfig.baseUrl : ApiConfig.baseUrlIOS}${ApiConfig.tokenRefreshEndpoint}',
        data: {'refresh': refreshToken},
      );

      if (response.statusCode == 200) {
        await _storage.write(key: 'access_token', value: response.data['access']);
        if (response.data['refresh'] != null) {
          await _storage.write(key: 'refresh_token', value: response.data['refresh']);
        }
        return true;
      }
    } catch (e) {
      _log.e('Token refresh failed', error: e);
    }
    return false;
  }

  // ─── Auth ───

  Future<Map<String, dynamic>> login(String username, String password) async {
    final response = await _dio.post(
      ApiConfig.tokenEndpoint,
      data: {'username': username, 'password': password},
    );
    await _storage.write(key: 'access_token', value: response.data['access']);
    await _storage.write(key: 'refresh_token', value: response.data['refresh']);
    return response.data;
  }

  Future<void> logout() async {
    await _storage.delete(key: 'access_token');
    await _storage.delete(key: 'refresh_token');
  }

  Future<bool> hasValidToken() async {
    final token = await _storage.read(key: 'access_token');
    return token != null;
  }

  // ─── Generic CRUD ───

  Future<Response> get(String path, {Map<String, dynamic>? queryParameters}) {
    return _dio.get(path, queryParameters: queryParameters);
  }

  Future<Response> post(String path, {dynamic data}) {
    return _dio.post(path, data: data);
  }

  Future<Response> put(String path, {dynamic data}) {
    return _dio.put(path, data: data);
  }

  Future<Response> patch(String path, {dynamic data}) {
    return _dio.patch(path, data: data);
  }

  Future<Response> delete(String path) {
    return _dio.delete(path);
  }

  // ─── Sync-specific ───

  Future<Map<String, dynamic>> pullChanges(DateTime? lastPulledAt) async {
    final response = await _dio.post(
      ApiConfig.syncPullEndpoint,
      data: {
        'last_pulled_at': lastPulledAt?.millisecondsSinceEpoch,
        'tables': [
          'categories', 'units', 'unit_conversions', 'items',
          'material_specs', 'product_specs',
          'warehouses', 'locations',
          'suppliers', 'customers',
          'stock_balances',
          'pos_registers', 'price_lists', 'price_list_items',
          'discount_rules', 'customer_price_catalogs',
          'users', 'roles', 'warehouse_permissions',
        ],
      },
    );
    return response.data;
  }

  Future<Map<String, dynamic>> pushChanges(Map<String, dynamic> changes) async {
    final response = await _dio.post(
      ApiConfig.syncPushEndpoint,
      data: changes,
    );
    return response.data;
  }
}

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient();
});
