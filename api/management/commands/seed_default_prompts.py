from django.core.management.base import BaseCommand

from api.models import CustomUser
from api.services.prompt_seeding import seed_default_prompts_for_user


class Command(BaseCommand):
    help = "Seed default prompts for users (backfill existing providers)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            default=None,
            help="Seed only for a specific user email.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing prompt_text/title with current defaults.",
        )

    def handle(self, *args, **options):
        email = (options.get("email") or "").strip()
        overwrite = bool(options.get("overwrite"))

        queryset = CustomUser.objects.all()
        if email:
            queryset = queryset.filter(email=email)

        users = list(queryset)
        if not users:
            target = f"email={email}" if email else "all users"
            self.stdout.write(self.style.WARNING(f"No users found for {target}."))
            return

        seeded_for_users = 0
        failed_users = 0
        total_inserted = 0
        total_updated = 0
        total_skipped = 0

        for user in users:
            try:
                result = seed_default_prompts_for_user(user, overwrite=overwrite)
                inserted = int(result.get("inserted", 0))
                updated = int(result.get("updated", 0))
                skipped = int(result.get("skipped", 0))
                total_inserted += inserted
                total_updated += updated
                total_skipped += skipped
                seeded_for_users += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"user={getattr(user, 'email', user.pk)} inserted={inserted} updated={updated} skipped={skipped}"
                    )
                )
            except Exception as exc:
                failed_users += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed for user={getattr(user, 'email', user.pk)}: {exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Done. "
                f"processed={len(users)} success={seeded_for_users} failed={failed_users} "
                f"inserted={total_inserted} updated={total_updated} skipped={total_skipped}"
            )
        )
