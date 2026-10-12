import * as Haptics from "expo-haptics";
import { useEffect, useRef, useState } from "react";
import { Platform, Pressable, View } from "react-native";

import { discardFailed, onSyncComplete, retryFailed, syncQueue, useSyncState } from "@/src/offline";
import { fonts, spacing, useTheme } from "@/src/theme";
import { Btn, Ionicons, Row, Sheet, T, useToast } from "@/src/ui";

// Threshold for the "تمت المزامنة" toast — only pop it when a meaningful
// backlog landed (avoids noise after single-item syncs).
const TOAST_THRESHOLD = 3;

// Shows connectivity + pending/failed offline actions. Hidden when all is synced.
// Includes a progress indicator for large flushes (thousands of items) and a
// quiet toast + haptic buzz on completion so owners know a reconnect catch-up
// finished.
export function SyncBanner() {
  const { colors } = useTheme();
  const toast = useToast();
  const { pending, failed, online, syncing, progress } = useSyncState();
  const [open, setOpen] = useState(false);
  // Keep the latest toast fn in a ref so onSyncComplete's one-time subscription
  // can always reach the current provider without re-subscribing per render.
  const toastRef = useRef(toast);
  toastRef.current = toast;
  useEffect(() => {
    const unsubscribe = onSyncComplete((synced) => {
      if (synced >= TOAST_THRESHOLD) {
        // Small success buzz on native so a connected device *feels* the moment
        // their backlog finally landed. The toast provider also triggers a
        // Success haptic, but running our own here ensures the buzz fires even
        // if the toast is suppressed for any reason (e.g. provider unmounted).
        if (Platform.OS !== "web") {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        }
        toastRef.current(`تمت المزامنة · ${synced} عملية`);
      }
    });
    return () => {
      unsubscribe();
    };
  }, []);
  if (online && !pending.length && !failed.length) return null;
  const tone = failed.length ? colors.error : online ? colors.info : colors.warning;
  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
  const text = !online
    ? `بدون اتصال · ${pending.length} عملية بانتظار المزامنة`
    : syncing && progress.total > 0
      ? `جارِ المزامنة · ${progress.done}/${progress.total} (${pct}%)`
      : syncing
        ? "جارِ المزامنة..."
        : failed.length
          ? `${failed.length} عملية فشلت مزامنتها`
          : `${pending.length} عملية بانتظار المزامنة`;
  return (
    <>
      <Pressable testID="sync-banner" onPress={() => setOpen(true)} style={{ backgroundColor: tone, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, gap: spacing.xs }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
          <Ionicons name={online ? "sync-outline" : "cloud-offline-outline"} size={18} color={colors.onInfo} />
          <T style={{ flex: 1, color: colors.onInfo, fontFamily: fonts.semibold, fontSize: 13 }}>{text}</T>
          <Ionicons name="chevron-back" size={16} color={colors.onInfo} />
        </View>
        {syncing && progress.total > 0 && (
          <View testID="sync-progress-bar" style={{ height: 3, borderRadius: 2, backgroundColor: "rgba(255,255,255,0.25)", overflow: "hidden" }}>
            <View style={{ width: `${pct}%`, height: 3, backgroundColor: "rgba(255,255,255,0.9)" }} />
          </View>
        )}
      </Pressable>
      <Sheet testID="sync-sheet" visible={open} onClose={() => setOpen(false)} title="المزامنة" footer={<Btn testID="sync-now-button" title="مزامنة الآن" icon="sync-outline" loading={syncing} onPress={syncQueue} />}>
        <T v="caption">العمليات المسجلة دون اتصال تُحفظ على الجهاز وتُرسل تلقائياً عند عودة الإنترنت. التعارضات تُحسم تلقائياً لصالح الخادم.</T>
        {syncing && progress.total > 0 && (
          <T v="caption" color="info">قيد المعالجة الآن: {progress.done} من أصل {progress.total}</T>
        )}
        {pending.map((p) => (
          <Row
            key={p.id}
            testID={`pending-item-${p.id}`}
            icon="time-outline"
            title={p.label}
            subtitle={(p.attempts ?? 0) > 0 ? `محاولة ${p.attempts}/5 · إعادة المحاولة قريباً` : "بانتظار المزامنة"}
          />
        ))}
        {failed.map((f) => (
          <View key={f.id}>
            <Row
              testID={`failed-item-${f.id}`}
              icon="alert-circle-outline"
              title={f.label}
              subtitle={f.error}
              right={
                <View style={{ flexDirection: "row", gap: spacing.xs }}>
                  <Btn small variant="secondary" title="إعادة" testID={`retry-failed-${f.id}`} onPress={() => retryFailed(f.id)} />
                  <Btn small variant="ghost" title="تجاهل" testID={`discard-failed-${f.id}`} onPress={() => discardFailed(f.id)} />
                </View>
              }
            />
          </View>
        ))}
        {!pending.length && !failed.length && <T>كل العمليات متزامنة</T>}
      </Sheet>
    </>
  );
}
