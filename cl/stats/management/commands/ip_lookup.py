import sys
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils.timezone import now

from cl.lib.redis_utils import get_redis_interface


class Command(BaseCommand):
    help = "Look up users associated with IP addresses from Redis API logs"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "ips",
            nargs="*",
            help="IP addresses to look up",
        )
        parser.add_argument(
            "--stdin",
            action="store_true",
            help="Read IP addresses from stdin (one per line)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=14,
            help="Number of days to search (default: 14)",
        )

    def handle(self, *args, **options) -> None:
        ips = list(options["ips"])

        if options["stdin"]:
            for line in sys.stdin:
                ip = line.strip()
                if ip:
                    ips.append(ip)

        if not ips:
            self.stderr.write("No IP addresses provided")
            return

        days = options["days"]
        found_ips: set[str] = set()
        r = get_redis_interface("STATS")

        self.stdout.write(
            f"Searching {len(ips)} IPs across last {days} days...\n"
        )
        self.stdout.write("-" * 80)

        # Search most recent days first
        for i in range(days):
            date_str = (now() - timedelta(days=i)).strftime("%Y-%m-%d")
            key = f"api:v4.d:{date_str}.ip_map"

            for ip in ips:
                if ip in found_ips:
                    continue

                user_pk = r.hget(key, ip)
                if user_pk:
                    found_ips.add(ip)
                    self._print_result(ip, user_pk, date_str)

        # Report IPs not found
        not_found = set(ips) - found_ips
        if not_found:
            self.stdout.write(f"\nNot found in last {days} days:")
            for ip in not_found:
                self.stdout.write(f"  {ip}")

        self.stdout.write("-" * 80)
        self.stdout.write(
            f"Found: {len(found_ips)}, Not found: {len(not_found)}"
        )

    def _print_result(self, ip: str, user_pk: str, date_str: str) -> None:
        try:
            user = User.objects.get(pk=int(user_pk))
            admin_url = reverse("admin:auth_user_change", args=[user.pk])
            self.stdout.write(
                f"\n{ip}\n"
                f"  User: {user.username} ({user.email})\n"
                f"  Date: {date_str}\n"
                f"  Admin: https://www.courtlistener.com{admin_url}\n"
                f"  Zoho: https://crm.zoho.com/crm/freelawproject/search"
                f"?searchword={user.pk}&isRelevance=false"
            )
        except User.DoesNotExist:
            self.stdout.write(
                f"\n{ip}\n"
                f"  User PK: {user_pk} (NOT FOUND IN DATABASE)\n"
                f"  Date: {date_str}"
            )
