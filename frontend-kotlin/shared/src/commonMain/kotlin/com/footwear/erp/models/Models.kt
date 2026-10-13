package com.footwear.erp.models

import kotlinx.serialization.Serializable

@Serializable
data class LoginResponse(
    val access_token: String,
    val token_type: String = "bearer",
    val user_id: Int,
    val username: String,
    val full_name: String,
    val role: String
)

@Serializable
data class UserProfile(
    val id: Int,
    val username: String,
    val email: String,
    val full_name: String,
    val role: String,
    val is_active: Boolean
)

@Serializable
data class BuyerSummary(
    val id: Int,
    val name: String,
    val buyer_code: String,
    val contact_person: String? = null,
    val phone: String? = null,
    val email: String? = null,
    val address: String? = null,
    val notes: String? = null,
    val is_active: Boolean,
    val created_at: String,
    val updated_at: String,
    val active_orders_count: Int = 0,
    val completed_orders_count: Int = 0,
    val total_ordered_pairs: Double = 0.0,
    val outstanding_production_pairs: Double = 0.0
)

@Serializable
data class OperationComponentDto(
    val id: Int,
    val operation_id: Int,
    val component_name: String,
    val unit: String,
    val pieces_per_pair: Double,
    val required_total_qty: Double,
    val accepted_total_qty: Double,
    val rejected_total_qty: Double,
    val balance_total_qty: Double,
    val pair_equivalent_accepted: Double = 0.0
)

@Serializable
data class OrderOperationDto(
    val id: Int,
    val route_id: Int,
    val operation_name: String,
    val sequence_order: Int,
    val unit: String,
    val required_quantity: Double,
    val completed_quantity: Double,
    val rejected_quantity: Double,
    val balance_quantity: Double,
    val completion_percentage: Double = 0.0,
    val daily_target: Double = 0.0,
    val start_date: String? = null,
    val expected_finish_date: String? = null,
    val status: String,
    val notes: String? = null,
    val components: List<OperationComponentDto> = emptyList()
)

@Serializable
data class OrderRouteDto(
    val id: Int,
    val order_id: Int,
    val section_id: Int,
    val section_name: String? = null,
    val category_name: String? = null,
    val status: String,
    val sequence_order: Int,
    val has_components: Boolean,
    val notes: String? = null,
    val operations: List<OrderOperationDto> = emptyList(),
    val is_completed: Boolean = false
)

@Serializable
data class DeliveryRevisionDto(
    val id: Int,
    val order_id: Int,
    val previous_delivery_date: String,
    val revised_delivery_date: String,
    val reason: String,
    val revised_by_id: Int,
    val revised_by_name: String? = null,
    val created_at: String
)

@Serializable
data class OrderSummaryDto(
    val id: Int,
    val order_code: String,
    val buyer_id: Int,
    val buyer_name: String? = null,
    val customer_ref: String,
    val po_number: String? = null,
    val style_model: String,
    val description: String? = null,
    val total_quantity: Double,
    val original_order_date: String,
    val production_start_date: String,
    val original_delivery_date: String,
    val current_delivery_date: String,
    val priority: String,
    val status: String,
    val notes: String? = null,
    val created_at: String,
    val updated_at: String,
    val remaining_working_days: Int = 0,
    val completed_pairs: Double = 0.0,
    val outstanding_pairs: Double = 0.0,
    val completion_percentage: Double = 0.0,
    val is_at_risk: Boolean = false,
    val is_overdue: Boolean = false
)

@Serializable
data class OrderDetailDto(
    val id: Int,
    val order_code: String,
    val buyer_id: Int,
    val buyer_name: String? = null,
    val customer_ref: String,
    val po_number: String? = null,
    val style_model: String,
    val description: String? = null,
    val total_quantity: Double,
    val original_order_date: String,
    val production_start_date: String,
    val original_delivery_date: String,
    val current_delivery_date: String,
    val priority: String,
    val status: String,
    val notes: String? = null,
    val created_at: String,
    val updated_at: String,
    val remaining_working_days: Int = 0,
    val completed_pairs: Double = 0.0,
    val outstanding_pairs: Double = 0.0,
    val completion_percentage: Double = 0.0,
    val is_at_risk: Boolean = false,
    val is_overdue: Boolean = false,
    val routes: List<OrderRouteDto> = emptyList(),
    val delivery_revisions: List<DeliveryRevisionDto> = emptyList()
)

@Serializable
data class DailyProductionEntryDto(
    val id: Int,
    val entry_date: String,
    val order_id: Int,
    val order_code: String? = null,
    val customer_ref: String? = null,
    val route_id: Int,
    val section_name: String? = null,
    val operation_id: Int,
    val operation_name: String? = null,
    val component_id: Int? = null,
    val component_name: String? = null,
    val quantity: Double,
    val accepted_quantity: Double,
    val rejected_quantity: Double,
    val unit: String,
    val remarks: String? = null,
    val entered_by_id: Int,
    val entered_by_name: String? = null,
    val created_at: String,
    val is_reversed: Boolean,
    val is_override: Boolean
)

@Serializable
data class SectionPerformanceDto(
    val section_id: Int,
    val section_name: String,
    val category_name: String,
    val total_planned_today: Double,
    val total_actual_today: Double,
    val variance: Double,
    val is_behind: Boolean
)

@Serializable
data class DashboardSummaryDto(
    val total_active_buyers: Int,
    val active_orders_count: Int,
    val total_ordered_pairs: Double,
    val completed_pairs: Double,
    val outstanding_production_pairs: Double,
    val orders_due_today: Int,
    val orders_due_7_days: Int,
    val overdue_orders_count: Int,
    val at_risk_orders_count: Int,
    val sections_behind_count: Int,
    val today_total_planned: Double,
    val today_total_actual: Double,
    val section_performances: List<SectionPerformanceDto> = emptyList()
)
