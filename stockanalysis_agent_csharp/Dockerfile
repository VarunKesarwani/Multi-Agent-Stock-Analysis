FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY StockAnalysis.Agent.Api.csproj ./
RUN dotnet restore StockAnalysis.Agent.Api.csproj
COPY . ./
RUN dotnet publish StockAnalysis.Agent.Api.csproj -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
COPY --from=build /app/publish ./
USER $APP_UID
EXPOSE 8080
ENTRYPOINT ["dotnet", "StockAnalysis.Agent.Api.dll"]

