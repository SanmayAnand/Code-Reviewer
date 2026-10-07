export const SAMPLES = [
  {
    name: "Python: long, deeply nested function",
    language: "python",
    code: `def process_orders(orders, tax, discount, region, currency, verbose):
    results = []
    for order in orders:
        if order.get("items"):
            for item in order["items"]:
                if item["qty"] > 0:
                    if region == "EU":
                        if item["price"] > 100:
                            total = item["price"] * item["qty"] * (1 + tax) * (1 - discount)
                        else:
                            total = item["price"] * item["qty"] * (1 + tax)
                    else:
                        total = item["price"] * item["qty"]
                    if verbose:
                        print("item", item["name"], total)
                    results.append({"name": item["name"], "total": total, "currency": currency})
    summary = {}
    for r in results:
        summary[r["name"]] = summary.get(r["name"], 0) + r["total"]
    lines = []
    for name, value in summary.items():
        lines.append(name + ": " + str(round(value, 2)) + " " + currency)
    return "\\n".join(lines)
`,
  },
  {
    name: "Python: god class with many dependencies",
    language: "python",
    code: `import smtplib, sqlite3, json

class UserManager:
    def __init__(self):
        self.db = sqlite3.connect("app.db")
        self.mailer = Mailer()
        self.logger = Logger()
        self.cache = Cache()
        self.cfg = json.load(open("cfg.json"))

    def create_user(self, name, email):
        self.db.execute("INSERT INTO users VALUES (?, ?)", (name, email))
        self.mailer.send(email, "Welcome")
        self.logger.info("created " + name)

    def delete_user(self, uid): ...
    def update_user(self, uid, data): ...
    def render_profile_html(self, uid): ...
    def export_csv(self): ...
    def import_csv(self, path): ...
    def charge_card(self, uid, amount): PaymentGateway().charge(uid, amount)
    def refund(self, uid): PaymentGateway().refund(uid)
    def send_newsletter(self): NewsletterBuilder().build(); self.mailer.send_all()
    def backup(self): BackupService().run()
    def audit(self): AuditTrail().write()
    def report(self): ReportEngine().generate()
    def sync_crm(self): CrmClient().sync()
    def health(self): HealthChecker().check()
`,
  },
  {
    name: "Java: complex method with a long parameter list",
    language: "java",
    code: `public class InvoiceService {
    private final TaxRepository taxRepo = new TaxRepository();

    public double calculate(String type, int qty, double price, double discount,
                            boolean member, String region, String coupon) {
        double total = 0;
        if (type.equals("A")) {
            if (qty > 10) {
                if (member && region.equals("EU")) {
                    total = qty * price * 0.8;
                } else if (member || coupon != null) {
                    total = qty * price * 0.9;
                } else {
                    total = qty * price;
                }
            } else {
                total = qty * price;
            }
        } else if (type.equals("B")) {
            for (int i = 0; i < qty; i++) {
                if (i % 2 == 0 && discount > 0) {
                    total += price * (1 - discount);
                } else {
                    total += price;
                }
            }
        }
        return total * (1 + taxRepo.rateFor(region));
    }
}
`,
  },
];
