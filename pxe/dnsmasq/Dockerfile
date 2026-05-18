FROM alpine:3
RUN apk add --no-cache dnsmasq
ENTRYPOINT ["dnsmasq", "-k"]
CMD ["--conf-file=/etc/dnsmasq.conf"]
