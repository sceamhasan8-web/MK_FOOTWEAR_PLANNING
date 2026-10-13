package com.footwear.erp.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.request.*
import io.ktor.client.request.forms.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.serialization.json.Json
import com.footwear.erp.models.*

class ErpApiClient(
    var baseUrl: String = "http://localhost:8000/api/v1"
) {
    var authToken: String? = null
    var currentUser: LoginResponse? = null

    val client = HttpClient {
        install(ContentNegotiation) {
            json(Json {
                ignoreUnknownKeys = true
                isLenient = true
                prettyPrint = true
            })
        }
    }

    private fun HttpRequestBuilder.attachAuth() {
        authToken?.let {
            header(HttpHeaders.Authorization, "Bearer $it")
        }
    }

    // ---------------- AUTHENTICATION ----------------
    suspend fun login(username: String, password: String):Result<LoginResponse> = runCatching {
        val response = client.submitForm(
            url = "$baseUrl/auth/login",
            formParameters = parameters {
                append("username", username)
                append("password", password)
            }
        )
        if (!response.status.isSuccess()) {
            val errorBody = response.bodyAsText()
            throw Exception("Login failed: $errorBody")
        }
        val loginData: LoginResponse = response.body()
        this.authToken = loginData.access_token
        this.currentUser = loginData
        loginData
    }

    // ---------------- BUYERS ----------------
    suspend fun getBuyers(search: String? = null): Result<List<BuyerSummary>> = runCatching {
        val response = client.get("$baseUrl/buyers") {
            attachAuth()
            search?.let { parameter("search", it) }
        }
        if (!response.status.isSuccess()) throw Exception(response.bodyAsText())
        response.body()
    }

    suspend fun createBuyer(
        name: String,
        buyerCode: String,
        contactPerson: String? = null,
        phone: String? = null,
        email: String? = null,
        address: String? = null
    ): Result<BuyerSummary> = runCatching {
        val response = client.post("$baseUrl/buyers") {
            attachAuth()
            contentType(ContentType.Application.Json)
            setBody(mapOf(
                "name" to name,
                "buyer_code" to buyerCode,
                "contact_person" to contactPerson,
                "phone" to phone,
                "email" to email,
                "address" to address,
                "is_active" to "true"
            ))
        }
        if (!response.status.isSuccess()) throw Exception(response.bodyAsText())
        response.body()
    }

    // ---------------- ORDERS ----------------
    suspend fun getOrders(buyerId: Int? = null, status: String? = null): Result<List<OrderSummaryDto>> = runCatching {
        val response = client.get("$baseUrl/orders") {
            attachAuth()
            buyerId?.let { parameter("buyer_id", it) }
            status?.let { parameter("order_status", it) }
        }
        if (!response.status.isSuccess()) throw Exception(response.bodyAsText())
        response.body()
    }

    suspend fun getOrderDetail(orderId: Int): Result<OrderDetailDto> = runCatching {
        val response = client.get("$baseUrl/orders/$orderId") {
            attachAuth()
        }
        if (!response.status.isSuccess()) throw Exception(response.bodyAsText())
        response.body()
    }

    suspend fun reviseDeliveryDate(orderId: Int, newDate: String, reason: String): Result<OrderDetailDto> = runCatching {
        val response = client.post("$baseUrl/orders/$orderId/revise-delivery-date") {
            attachAuth()
            contentType(ContentType.Application.Json)
            setBody(mapOf(
                "revised_delivery_date" to newDate,
                "reason" to reason
            ))
        }
        if (!response.status.isSuccess()) throw Exception(response.bodyAsText())
        response.body()
    }

    // ---------------- PRODUCTION ENTRIES ----------------
    suspend fun recordProductionEntry(
        orderId: Int,
        routeId: Int,
        operationId: Int,
        componentId: Int? = null,
        entryDate: String,
        quantity: Double,
        acceptedQty: Double,
        rejectedQty: Double = 0.0,
        unit: String = "PAIRS",
        remarks: String? = null,
        isOverride: Boolean = false
    ): Result<DailyProductionEntryDto> = runCatching {
        val response = client.post("$baseUrl/production/entry") {
            attachAuth()
            contentType(ContentType.Application.Json)
            val bodyMap = mutableMapOf<String, Any>(
                "order_id" to orderId,
                "route_id" to routeId,
                "operation_id" to operationId,
                "entry_date" to entryDate,
                "quantity" to quantity,
                "accepted_quantity" to acceptedQty,
                "rejected_quantity" to rejectedQty,
                "unit" to unit,
                "is_override" to isOverride
            )
            componentId?.let { bodyMap["component_id"] = it }
            remarks?.let { bodyMap["remarks"] = it }

            setBody(bodyMap)
        }
        if (!response.status.isSuccess()) throw Exception(response.bodyAsText())
        response.body()
    }

    suspend fun getProductionEntries(orderId: Int? = null): Result<List<DailyProductionEntryDto>> = runCatching {
        val response = client.get("$baseUrl/production/entries") {
            attachAuth()
            orderId?.let { parameter("order_id", it) }
        }
        if (!response.status.isSuccess()) throw Exception(response.bodyAsText())
        response.body()
    }

    // ---------------- DASHBOARD ----------------
    suspend fun getDashboardSummary(): Result<DashboardSummaryDto> = runCatching {
        val response = client.get("$baseUrl/dashboard/summary") {
            attachAuth()
        }
        if (!response.status.isSuccess()) throw Exception(response.bodyAsText())
        response.body()
    }

    // ---------------- EXPORTS ----------------
    fun getOrderXlsxUrl(orderId: Int): String = "$baseUrl/exports/orders/$orderId/xlsx"
    fun getOrderCsvUrl(orderId: Int): String = "$baseUrl/exports/orders/$orderId/csv"
}
