import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/sign_in_screen.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/invites/accept_invite_screen.dart';
import '../features/occurrence/occurrence_screen.dart';
import '../features/occurrence/occurrence_summary_screen.dart';
import '../features/series/series_screen.dart';
import '../features/room/room_screen.dart';
import '../services/auth_service.dart';

GoRouter buildRouter(AuthService auth) {
  return GoRouter(
    refreshListenable: auth,
    redirect: (context, state) {
      final signedIn = auth.isSignedIn;
      final goingToSignIn = state.matchedLocation == '/sign-in';

      if (!signedIn && !goingToSignIn &&
          !state.matchedLocation.startsWith('/invites/')) {
        return '/sign-in';
      }
      if (signedIn && goingToSignIn) {
        return '/';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/sign-in',
        builder: (context, state) => const SignInScreen(),
      ),
      GoRoute(
        path: '/',
        builder: (context, state) => const DashboardScreen(),
      ),
      GoRoute(
        path: '/rooms/:id',
        builder: (context, state) =>
            RoomScreen(roomId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/series/:id',
        builder: (context, state) =>
            SeriesScreen(seriesId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/occurrences/:id',
        builder: (context, state) =>
            OccurrenceScreen(occurrenceId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/occurrences/:id/summary',
        builder: (context, state) =>
            OccurrenceSummaryScreen(occurrenceId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/invites/:id',
        builder: (context, state) =>
            AcceptInviteScreen(inviteId: state.pathParameters['id']!),
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      body: Center(child: Text('Page not found: ${state.uri}')),
    ),
  );
}
