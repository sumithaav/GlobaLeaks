GL.
controller("ConfirmableModalCtrl",
           ["$scope", "$uibModalInstance", "arg", "confirmFun", "cancelFun", function($scope, $uibModalInstance, arg, confirmFun, cancelFun) {
  $scope.arg = arg;
  $scope.confirmFun = confirmFun;
  $scope.cancelFun = cancelFun;

  $scope.confirm = function(result) {
    if ($scope.confirmFun) {
      $scope.confirmFun(result);
    }

    return $uibModalInstance.close(result);
  };

  $scope.cancel = function(result) {
    if ($scope.cancelFun) {
      $scope.cancelFun(result);
    }

    return $uibModalInstance.dismiss("cancel");
  };
}]).controller("ViewModalCtrl", ["$scope", "$uibModalInstance", "arg", "confirmFun", "cancelFun", function($scope, $uibModalInstance, arg, confirmFun, cancelFun) {
  $scope.arg = arg;
  $scope.confirmFun = confirmFun;
  $scope.cancelFun = cancelFun;
  console.log("arguments got => ", arg);

  $scope.cancel = function(result) {
    if ($scope.cancelFun) {
      $scope.cancelFun(result);
    }

    return $uibModalInstance.dismiss("cancel");
  };
  $scope.getFileTag = function(type) {
    var tag = "none";

    // if type is an image then return image
    if (type.indexOf("image") > -1) {
      tag = "image";
    }

    // if file is a pdf then return pdf
    if (type.indexOf("pdf") > -1) {
      tag = "pdf";
    }

    // if file is an video of mp4 then return video
    if (type.indexOf("video") > -1) {
      tag = "video";
    }

    // if video is mp3 then return audio
    if (type.indexOf("audio") > -1) {
      tag = "audio";
    }
    return tag;
  };

}]);
