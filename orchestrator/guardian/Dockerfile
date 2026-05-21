FROM docker:cli
RUN apk add --no-cache bash python3 coreutils

# Copy guardian entrypoint into a non-mounted path
COPY scripts/guardian_loop.sh /guardian/entrypoint/guardian_loop.sh
COPY scripts/external_cron_guardian.sh /guardian/entrypoint/external_cron_guardian.sh
RUN chmod +x /guardian/entrypoint/guardian_loop.sh /guardian/entrypoint/external_cron_guardian.sh

ENTRYPOINT ["bash", "/guardian/entrypoint/guardian_loop.sh"]
