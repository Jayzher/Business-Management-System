import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'config/app_theme.dart';
import 'config/app_router.dart';
import 'services/connectivity_service.dart';
import 'sync/sync_engine.dart';
import 'database/app_database.dart';

class BusinessApp extends ConsumerStatefulWidget {
  const BusinessApp({super.key});

  @override
  ConsumerState<BusinessApp> createState() => _BusinessAppState();
}

class _BusinessAppState extends ConsumerState<BusinessApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Start connectivity monitoring and initial sync
    Future.microtask(() {
      ref.read(connectivityServiceProvider);
      ref.read(syncEngineProvider).initialSync();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      ref.read(syncEngineProvider).syncIfNeeded();
    }
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(appRouterProvider);

    return MaterialApp.router(
      title: 'Business Management',
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.system,
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}
