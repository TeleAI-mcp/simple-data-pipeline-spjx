"""
FastAPI main application class.
"""

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Type, Union

from fastapi import routing
from fastapi.concurrency import run_in_threadpool
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.dependencies.utils import (
    get_body_field,
    get_dependant,
    get_typed_return_annotation,
    solve_dependencies,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.logger import logger
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.openapi.utils import get_openapi
from fastapi.params import Depends
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.types import ASGIApp, ASGIInstance, Receive, Scope, Send
from fastapi.utils import (
    generate_operation_id_for_path,
    get_application_state,
    is_body_allowed_for_status_code,
)
from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.exceptions import ExceptionMiddleware
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.errors import ServerErrorMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import BaseRoute, Match, Mount
from starlette.types import ASGIApp, Receive, Scope, Send


class FastAPI(Starlette):
    """
    The main class in FastAPI that provides all the functionality for the app.

    This class inherits from Starlette so you can use Starlette's functionality.
    """

    def __init__(
        self,
        *,
        debug: bool = False,
        routes: Optional[List[BaseRoute]] = None,
        title: str = "FastAPI",
        description: str = "",
        version: str = "0.1.0",
        openapi_url: Optional[str] = "/openapi.json",
        openapi_tags: Optional[List[Dict[str, Any]]] = None,
        servers: Optional[List[Dict[str, Union[str, Any]]]] = None,
        dependencies: Optional[Sequence[Depends]] = None,
        default_response_class: Type[Response] = Default(JSONResponse),
        docs_url: Optional[str] = "/docs",
        redoc_url: Optional[str] = "/redoc",
        swagger_ui_oauth2_redirect_url: Optional[str] = "/docs/oauth2-redirect",
        swagger_ui_init_oauth: Optional[Dict[str, Any]] = None,
        middleware: Optional[List[Middleware]] = None,
        exception_handlers: Optional[
            Dict[Union[int, Type[Exception]], Callable[[Request, Any], Any]]
        ] = None,
        on_startup: Optional[Sequence[Callable[[], Any]]] = None,
        on_shutdown: Optional[Sequence[Callable[[], Any]]] = None,
        terms_of_service: Optional[str] = None,
        contact: Optional[Dict[str, Union[str, Any]]] = None,
        license_info: Optional[Dict[str, Union[str, Any]]] = None,
        openapi_prefix: str = "",
        root_path: str = "",
        root_path_in_servers: bool = True,
        responses: Optional[Dict[Union[int, str], Dict[str, Any]]] = None,
        callbacks: Optional[List[BaseRoute]] = None,
        webhooks: Optional[routing.APIRouter] = None,
        deprecated: Optional[bool] = None,
        include_in_schema: bool = True,
        swagger_ui_parameters: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> None:
        """
        Initialize a FastAPI application.

        Args:
            debug: Enable debug mode.
            routes: List of routes.
            title: Title of the API.
            description: Description of the API.
            version: Version of the API.
            openapi_url: URL for the OpenAPI schema.
            openapi_tags: Tags for the OpenAPI schema.
            servers: List of servers for the OpenAPI schema.
            dependencies: Global dependencies.
            default_response_class: Default response class.
            docs_url: URL for the Swagger UI docs.
            redoc_url: URL for the ReDoc docs.
            swagger_ui_oauth2_redirect_url: URL for the OAuth2 redirect.
            swagger_ui_init_oauth: OAuth2 configuration for Swagger UI.
            middleware: List of middleware.
            exception_handlers: Exception handlers.
            on_startup: Startup event handlers.
            on_shutdown: Shutdown event handlers.
            terms_of_service: Terms of service.
            contact: Contact information.
            license_info: License information.
            openapi_prefix: Prefix for the OpenAPI schema.
            root_path: Root path for the application.
            root_path_in_servers: Whether to include root_path in servers.
            responses: Default responses.
            callbacks: Callbacks.
            webhooks: Webhooks.
            deprecated: Whether the API is deprecated.
            include_in_schema: Whether to include in schema.
            swagger_ui_parameters: Parameters for Swagger UI.
            **extra: Additional parameters.
        """
        self._debug = debug
        self.state: Dict[str, Any] = {}
        self.router: routing.APIRouter = routing.APIRouter(
            routes=routes,
            dependency_overrides_provider=self,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            default_response_class=default_response_class,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            responses=responses,
            callbacks=callbacks,
            webhooks=webhooks,
        )
        self.openapi_schema: Optional[Dict[str, Any]] = None
        self.openapi_version: str = "3.1.0"
        self.openapi_url: Optional[str] = openapi_url
        self.openapi_tags: Optional[List[Dict[str, Any]]] = openapi_tags
        self.servers: Optional[List[Dict[str, Union[str, Any]]]] = servers
        self.docs_url: Optional[str] = docs_url
        self.redoc_url: Optional[str] = redoc_url
        self.swagger_ui_oauth2_redirect_url: Optional[str] = swagger_ui_oauth2_redirect_url
        self.swagger_ui_init_oauth: Optional[Dict[str, Any]] = swagger_ui_init_oauth
        self.title: str = title
        self.description: str = description
        self.version: str = version
        self.terms_of_service: Optional[str] = terms_of_service
        self.contact: Optional[Dict[str, Union[str, Any]]] = contact
        self.license_info: Optional[Dict[str, Union[str, Any]]] = license_info
        self.openapi_prefix: str = openapi_prefix
        self.root_path: str = root_path
        self.root_path_in_servers: bool = root_path_in_servers
        self.swagger_ui_parameters: Optional[Dict[str, Any]] = swagger_ui_parameters
        self.extra: Dict[str, Any] = extra
        self.dependency_overrides: Dict[Callable[..., Any], Callable[..., Any]] = {}
        self.user_middleware: List[Middleware] = middleware or []
        self.middleware_stack: ASGIApp = self.build_middleware_stack()
        self.exception_handlers: Dict[
            Union[int, Type[Exception]], Callable[[Request, Any], Any]
        ] = exception_handlers or {}

        self.setup()

    def setup(self) -> None:
        """Set up the application."""
        if self.openapi_url:
            assert self.openapi_url.startswith(
                "/"
            ), "openapi_url should start with /"
            self.add_route(
                self.openapi_url,
                lambda r: JSONResponse(self.openapi()),
                include_in_schema=False,
            )
        if self.openapi_url and self.docs_url:
            assert self.docs_url.startswith("/"), "docs_url should start with /"
            self.add_route(
                self.docs_url,
                lambda r: get_swagger_ui_html(
                    openapi_url=self.openapi_url + self.root_path,
                    title=self.title + " - Swagger UI",
                    oauth2_redirect_url=self.swagger_ui_oauth2_redirect_url,
                    init_oauth=self.swagger_ui_init_oauth,
                    swagger_ui_parameters=self.swagger_ui_parameters,
                ),
                include_in_schema=False,
            )
            if self.swagger_ui_oauth2_redirect_url:
                assert (
                    self.swagger_ui_oauth2_redirect_url.startswith("/")
                ), "swagger_ui_oauth2_redirect_url should start with /"
                self.add_route(
                    self.swagger_ui_oauth2_redirect_url,
                    lambda r: get_swagger_ui_oauth2_redirect_html(),
                    include_in_schema=False,
                )
        if self.openapi_url and self.redoc_url:
            assert self.redoc_url.startswith("/"), "redoc_url should start with /"
            self.add_route(
                self.redoc_url,
                lambda r: get_redoc_html(
                    openapi_url=self.openapi_url + self.root_path,
                    title=self.title + " - ReDoc",
                ),
                include_in_schema=False,
            )

    def openapi(self) -> Dict[str, Any]:
        """Generate the OpenAPI schema."""
        if not self.openapi_schema:
            self.openapi_schema = get_openapi(
                title=self.title,
                version=self.version,
                description=self.description,
                routes=self.routes,
                tags=self.openapi_tags,
                servers=self.servers,
                terms_of_service=self.terms_of_service,
                contact=self.contact,
                license_info=self.license_info,
                openapi_prefix=self.openapi_prefix,
                openapi_version=self.openapi_version,
                separate_input_output_schemas=False,
            )
        return self.openapi_schema

    def include_router(
        self,
        router: routing.APIRouter,
        *,
        prefix: str = "",
        tags: Optional[List[str]] = None,
        dependencies: Optional[Sequence[Depends]] = None,
        responses: Optional[Dict[Union[int, str], Dict[str, Any]]] = None,
        deprecated: Optional[bool] = None,
        include_in_schema: bool = True,
        default_response_class: Optional[Type[Response]] = Default(JSONResponse),
        callbacks: Optional[List[BaseRoute]] = None,
        generate_unique_id_function: Callable[[routing.APIRoute], str] = Default(
            generate_operation_id_for_path
        ),
    ) -> None:
        """
        Include a router in the application.

        Args:
            router: The router to include.
            prefix: Prefix for the router.
            tags: Tags for the router.
            dependencies: Dependencies for the router.
            responses: Default responses.
            deprecated: Whether the router is deprecated.
            include_in_schema: Whether to include in schema.
            default_response_class: Default response class.
            callbacks: Callbacks.
            generate_unique_id_function: Function to generate unique IDs.
        """
        self.router.include_router(
            router,
            prefix=prefix,
            tags=tags,
            dependencies=dependencies,
            responses=responses,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            default_response_class=default_response_class,
            callbacks=callbacks,
            generate_unique_id_function=generate_unique_id_function,
        )

    def add_route(
        self,
        path: str,
        route: Union[Type[BaseRoute], BaseRoute, Callable],
        *,
        methods: Optional[List[str]] = None,
        name: Optional[str] = None,
        include_in_schema: bool = True,
    ) -> None:
        """
        Add a route to the application.

        Args:
            path: The path for the route.
            route: The route to add.
            methods: HTTP methods.
            name: Name of the route.
            include_in_schema: Whether to include in schema.
        """
        self.router.add_route(
            path,
            route,
            methods=methods,
            name=name,
            include_in_schema=include_in_schema,
        )

    def add_websocket_route(
        self,
        path: str,
        route: Union[Type[BaseRoute], BaseRoute, Callable],
        name: Optional[str] = None,
    ) -> None:
        """
        Add a WebSocket route to the application.

        Args:
            path: The path for the WebSocket route.
            route: The WebSocket route to add.
            name: Name of the route.
        """
        self.router.add_websocket_route(path, route, name=name)

    def add_middleware(
        self,
        middleware_class: Type[BaseHTTPMiddleware],
        **options: Any,
    ) -> None:
        """
        Add middleware to the application.

        Args:
            middleware_class: The middleware class to add.
            **options: Additional options for the middleware.
        """
        self.user_middleware.insert(0, Middleware(middleware_class, **options))
        self.middleware_stack = self.build_middleware_stack()

    def build_middleware_stack(self) -> ASGIApp:
        """Build the middleware stack."""
        app = self.router
        for middleware in reversed(self.user_middleware):
            app = middleware.cls(app=app, **middleware.options)
        error_handler = ServerErrorMiddleware(
            app=app, debug=self._debug, handler=self.exception_handlers
        )
        return error_handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle ASGI calls."""
        scope["root_path"] = self.root_path
        await self.middleware_stack(scope, receive, send)
