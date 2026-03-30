import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app/router.dart';
import 'app/theme.dart';
import 'firebase_options.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  runApp(const EventLedgerApp());
}

class EventLedgerApp extends StatelessWidget {
  const EventLedgerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AuthService(),
      child: Builder(
        builder: (context) {
          final auth = context.watch<AuthService>();
          return Provider(
            create: (_) => ApiService(auth),
            child: MaterialApp.router(
              title: 'Event Ledger',
              theme: AppTheme.light,
              routerConfig: buildRouter(auth),
              debugShowCheckedModeBanner: false,
            ),
          );
        },
      ),
    );
  }
}
