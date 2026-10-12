import { RoleTabs } from "@/src/RoleTabs";

export default function DistributorLayout() {
  return (
    <RoleTabs
      tourKey="dist"
      tabs={[
        { name: "index", title: "الرئيسية", icon: "home-outline", sf: "house.fill", desc: "مبيعاتك ومخزونك وهدفك الشهري، خط السير اليومي، والبضاعة بانتظار الاستلام." },
        { name: "sale", title: "بيع", icon: "cart-outline", sf: "cart.fill", desc: "أنشئ فاتورة مبيعات جديدة بالقطعة أو بالكرتونة، نقداً أو آجلاً." },
        { name: "sales", title: "الفواتير", icon: "receipt-outline", sf: "doc.text.fill", desc: "فواتيرك ومرتجعاتك مع الطباعة والمشاركة PDF." },
        { name: "customers", title: "العملاء", icon: "people-outline", sf: "person.2.fill", desc: "أضف عملاءك وأرسل كشف الحساب PDF بضغطة واحدة." },
        { name: "ops", title: "العمليات", icon: "wallet-outline", sf: "banknote.fill", desc: "سندات القبض والصرف، المرتجعات، وإرجاع البضاعة للمستودع." },
      ]}
    />
  );
}
