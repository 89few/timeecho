class ApiResponse<T> {
  const ApiResponse({
    required this.success,
    this.data,
    this.message,
    this.errorCode,
  });

  final bool success;
  final T? data;
  final String? message;
  final String? errorCode;
}
