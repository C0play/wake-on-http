build:
	docker buildx build --platform=linux/amd64,linux/arm64 --tag git.blazejjakubowski.com/blazej/$(NAME) --push .
