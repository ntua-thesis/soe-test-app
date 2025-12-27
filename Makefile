REGISTRY = nexus.lefto.org/docker
NAME = soe-test-app
VERSION = 0.0.1-8bit

docker:
		docker build . -t $(NAME):$(VERSION)
		docker tag $(NAME):$(VERSION) $(REGISTRY)/$(NAME):$(VERSION)
		docker push $(REGISTRY)/$(NAME):$(VERSION)
		