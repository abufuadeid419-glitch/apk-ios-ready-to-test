import { useMemo, useState } from "react";
import { View } from "react-native";

import { fmtDate, money } from "@/src/api";
import { DocActions } from "@/src/components/DocActions";
import { useApi } from "@/src/hooks";
import { shareReceipt } from "@/src/printDoc";
import { SupplierStatement, supplierStatementReceipt } from "@/src/receipts";
import { spacing } from "@/src/theme";
import { Btn, Card, Empty, IconBtn, Loading, Row, Sheet, T, useToast } from "@/src/ui";

// Group warehouse purchases + purchase returns by supplier name.
function group(purchases: any[], returns: any[]): SupplierStatement[] {
  const m = new Map<string, SupplierStatement>();
  const get = (name: string) => {
    const k = name.trim() || "بدون مورد";
    if (!m.has(k)) m.set(k, { name: k, rows: [], balance: 0 });
    return m.get(k)!;
  };
  for (const p of purchases) get(p.supplier ?? "").rows.push({ type: "PURCHASE", ref: "", product: p.product_name, quantity: p.quantity, debit: 0, credit: p.total ?? 0, date: p.created_at });
  for (const r of returns) get(r.supplier ?? "").rows.push({ type: "PURCHASE_RETURN", ref: r.return_no ?? "", product: r.product_name, quantity: r.quantity, debit: r.total ?? 0, credit: 0, date: r.created_at });
  const list = [...m.values()];
  for (const s of list) {
    s.rows.sort((a, b) => String(a.date).localeCompare(String(b.date)));
    s.balance = s.rows.reduce((b, x) => b + x.credit - x.debit, 0);
  }
  return list.sort((a, b) => b.balance - a.balance);
}

const waText = (s: SupplierStatement, org: any) =>
  [`*${org?.name ?? ""}*`, `كشف حساب المورد: ${s.name}`, `التاريخ: ${fmtDate(new Date().toISOString())}`, `عدد الحركات: ${s.rows.length}`, `*المستحق للمورد: ${money(s.balance)} ${org?.currency ?? ""}*`].join("\n");

export function SupplierStatementsSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const toast = useToast();
  const purchases = useApi<any[]>("/purchases", visible);
  const returns = useApi<any[]>("/purchase-returns", visible);
  const org = useApi<any>("/org/profile", visible);
  const logo = useApi<any>("/org/logo", visible);
  const [sel, setSel] = useState<string | null>(null);
  const suppliers = useMemo(() => group(purchases.data ?? [], returns.data ?? []), [purchases.data, returns.data]);
  const current = suppliers.find((s) => s.name === sel) ?? null;
  const make = (s: SupplierStatement) => supplierStatementReceipt(s, org.data, logo.data?.data_uri ?? null);
  const shareNow = (s: SupplierStatement) => shareReceipt(make(s), `كشف حساب مورد - ${s.name}`).catch((e: any) => toast(e?.message ?? "تعذر إنشاء الملف", "error"));
  const close = () => {
    setSel(null);
    onClose();
  };

  return (
    <Sheet testID="supplier-statements-sheet" visible={visible} onClose={close} title={current ? `كشف حساب: ${current.name}` : "كشوف حساب الموردين"}>
      {purchases.isLoading || returns.isLoading ? (
        <Loading />
      ) : current ? (
        <>
          <Btn testID="supplier-back-button" small variant="ghost" icon="arrow-forward" title="كل الموردين" onPress={() => setSel(null)} />
          <Card style={{ gap: spacing.xs }}>
            <T v="h2">{current.name}</T>
            <T v="caption">{current.rows.length} حركة</T>
            <T v="label" color="warning" testID="supplier-balance">المستحق للمورد: {money(current.balance)}</T>
          </Card>
          <DocActions idPrefix="supplier-statement" title={`كشف حساب مورد - ${current.name}`} waTitle="إرسال ملخص واتساب" make={() => make(current)} waText={() => waText(current, org.data)} />
          {current.rows.map((r, i) => (
            <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <View style={{ flex: 1 }}>
                <T v="label">{r.type === "PURCHASE" ? "مشتريات" : `مرتجع ${r.ref}`} · {r.product} × {money(r.quantity)}</T>
                <T v="caption">{fmtDate(r.date)}</T>
              </View>
              <T v="label" color={r.credit ? "warning" : "success"}>{money(r.credit || r.debit)}</T>
            </View>
          ))}
        </>
      ) : !suppliers.length ? (
        <Empty icon="people-outline" text="لا توجد مشتريات من موردين بعد" />
      ) : (
        <>
          <T v="caption">اضغط أيقونة المشاركة لإرسال كشف حساب PDF للمورد بضغطة واحدة</T>
          {suppliers.map((s, i) => (
            <Row
              key={s.name}
              testID={`supplier-row-${i}`}
              icon="storefront-outline"
              title={s.name}
              subtitle={`${s.rows.length} حركة · المستحق ${money(s.balance)}`}
              onPress={() => setSel(s.name)}
              right={<IconBtn testID={`supplier-share-pdf-${i}`} icon="share-outline" tone="brand" onPress={() => shareNow(s)} />}
            />
          ))}
        </>
      )}
    </Sheet>
  );
}
