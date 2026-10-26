FROM golang:1-alpine AS build
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 go build -trimpath -o /server .
FROM scratch
COPY --from=build /server /server
USER 10001:10001
ENTRYPOINT ["/server"]
