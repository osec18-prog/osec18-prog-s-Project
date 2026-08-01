import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../state/app_state.dart';
import '../../theme.dart';

/// Camera QR scanner. Pops `true` when attendance was recorded so the caller
/// can refresh the attendance list.
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

enum _ScanState { scanning, sending, done, failed }

class _ScanScreenState extends State<ScanScreen> {
  final MobileScannerController _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
    facing: CameraFacing.back,
  );

  _ScanState _state = _ScanState.scanning;
  String _message = 'Point the camera at the attendance QR code.';
  bool _recorded = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_state != _ScanState.scanning) return;

    final raw = capture.barcodes
        .map((barcode) => barcode.rawValue)
        .firstWhere((value) => value != null && value.trim().isNotEmpty, orElse: () => null);

    if (raw == null) return;

    setState(() {
      _state = _ScanState.sending;
      _message = 'Recording attendance…';
    });

    await _controller.stop();

    try {
      final message = await appState.api.scanAttendance(raw.trim());
      if (!mounted) return;
      setState(() {
        _state = _ScanState.done;
        _message = message;
        _recorded = true;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _state = _ScanState.failed;
        _message = error.toString();
      });
    }
  }

  Future<void> _scanAgain() async {
    setState(() {
      _state = _ScanState.scanning;
      _message = 'Point the camera at the attendance QR code.';
    });
    await _controller.start();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Scan attendance QR'),
        actions: [
          IconButton(
            tooltip: 'Toggle torch',
            onPressed: () => _controller.toggleTorch(),
            icon: const Icon(Icons.flashlight_on_outlined),
          ),
          IconButton(
            tooltip: 'Switch camera',
            onPressed: () => _controller.switchCamera(),
            icon: const Icon(Icons.cameraswitch_outlined),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Stack(
              fit: StackFit.expand,
              children: [
                MobileScanner(
                  controller: _controller,
                  onDetect: _onDetect,
                  errorBuilder: (context, error, child) => Center(
                    child: Padding(
                      padding: const EdgeInsets.all(28),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.videocam_off, color: Colors.white70, size: 48),
                          const SizedBox(height: 14),
                          Text(
                            'Camera unavailable.\n${error.errorDetails?.message ?? error.errorCode.name}',
                            textAlign: TextAlign.center,
                            style: const TextStyle(color: Colors.white70),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                IgnorePointer(
                  child: Center(
                    child: Container(
                      width: 250,
                      height: 250,
                      decoration: BoxDecoration(
                        border: Border.all(color: Colors.white70, width: 3),
                        borderRadius: BorderRadius.circular(24),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          _ResultPanel(
            state: _state,
            message: _message,
            onScanAgain: _scanAgain,
            onDone: () => Navigator.pop(context, _recorded),
          ),
        ],
      ),
    );
  }
}

class _ResultPanel extends StatelessWidget {
  const _ResultPanel({
    required this.state,
    required this.message,
    required this.onScanAgain,
    required this.onDone,
  });

  final _ScanState state;
  final String message;
  final VoidCallback onScanAgain;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    late final IconData icon;
    late final Color color;

    switch (state) {
      case _ScanState.scanning:
        icon = Icons.qr_code_scanner;
        color = Colors.white;
      case _ScanState.sending:
        icon = Icons.cloud_upload_outlined;
        color = kBrandAmber;
      case _ScanState.done:
        icon = Icons.check_circle;
        color = kBrandMint;
      case _ScanState.failed:
        icon = Icons.error;
        color = kBrandRose;
    }

    return Container(
      width: double.infinity,
      color: const Color(0xFF11162A),
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
      child: Column(
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (state == _ScanState.sending)
                const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2, color: kBrandAmber),
                )
              else
                Icon(icon, color: color, size: 24),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  message,
                  style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.35),
                ),
              ),
            ],
          ),
          if (state == _ScanState.done || state == _ScanState.failed) ...[
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: onScanAgain,
                    style: OutlinedButton.styleFrom(foregroundColor: Colors.white),
                    child: const Text('Scan again'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    onPressed: onDone,
                    child: const Text('Done'),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
