import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:logger/logger.dart';

final _log = Logger();

enum ConnectionStatus { online, offline }

class ConnectivityService {
  final Connectivity _connectivity = Connectivity();
  final _controller = StreamController<ConnectionStatus>.broadcast();

  ConnectionStatus _status = ConnectionStatus.offline;
  ConnectionStatus get status => _status;
  Stream<ConnectionStatus> get statusStream => _controller.stream;
  bool get isOnline => _status == ConnectionStatus.online;

  ConnectivityService() {
    _init();
  }

  void _init() {
    _connectivity.onConnectivityChanged.listen((results) {
      final hasConnection = results.any((r) => r != ConnectivityResult.none);
      final newStatus = hasConnection ? ConnectionStatus.online : ConnectionStatus.offline;
      if (newStatus != _status) {
        _status = newStatus;
        _controller.add(_status);
        _log.i('Connectivity changed: $_status');
      }
    });

    // Check initial status
    _connectivity.checkConnectivity().then((results) {
      _status = results.any((r) => r != ConnectivityResult.none)
          ? ConnectionStatus.online
          : ConnectionStatus.offline;
      _controller.add(_status);
    });
  }

  void dispose() {
    _controller.close();
  }
}

final connectivityServiceProvider = Provider<ConnectivityService>((ref) {
  final service = ConnectivityService();
  ref.onDispose(() => service.dispose());
  return service;
});

final connectivityStreamProvider = StreamProvider<ConnectionStatus>((ref) {
  return ref.watch(connectivityServiceProvider).statusStream;
});
